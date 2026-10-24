<?php
declare(strict_types=1);

final class PromoResult extends RuntimeException {
    public string $status;
    public int $httpStatus;
    public function __construct(string $status, int $httpStatus) {
        parent::__construct($status);
        $this->status = $status;
        $this->httpStatus = $httpStatus;
    }
}

function promo_connect(array $config): PDO {
    $dsn = (string)($config['db_dsn'] ?? '');
    if (!str_starts_with($dsn, 'mysql:')) {
        throw new RuntimeException('MySQL DSN required');
    }
    $options = [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_EMULATE_PREPARES => false, PDO::ATTR_TIMEOUT => 5];
    $ca = (string)($config['db_ssl_ca'] ?? '');
    preg_match('/(?:^|;)host=([^;]+)/', substr($dsn, 6), $matches);
    $host = $matches[1] ?? '';
    $local = in_array($host, ['localhost', '127.0.0.1', '::1'], true);
    $privateIp = filter_var($host, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) && preg_match('/\A(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)/', $host);
    $privateConnection = ($config['db_private_network'] ?? false) === true && $privateIp;
    if ($ca !== '') {
        if (!is_file($ca)) { throw new RuntimeException('Database CA unavailable'); }
        $options[PDO::MYSQL_ATTR_SSL_CA] = $ca;
        $options[PDO::MYSQL_ATTR_SSL_VERIFY_SERVER_CERT] = true;
    } elseif (!$local && !$privateConnection) {
        throw new RuntimeException('External MySQL requires a verified CA');
    }
    $db = new PDO($dsn, (string)$config['db_user'], (string)$config['db_password'], $options);
    $db->exec('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED');
    $db->exec('SET SESSION innodb_lock_wait_timeout=5');
    return $db;
}

function promo_receipt(string $hash, string $request): array {
    return ['status' => 'activated', 'credits' => 1, 'code_hash' => $hash, 'request_id' => $request];
}

function promo_activate(PDO $db, string $code, string $token, string $request): array {
    $code = trim($code);
    if ($code === '' || strlen($code) > 256 || str_contains($code, "\n") || str_contains($code, "\r") ||
        !preg_match('/\A[a-f0-9]{64}\z/', $token) || !preg_match('/\A[a-f0-9]{32}\z/', $request)) {
        throw new PromoResult('invalid_request', 400);
    }
    $hash = hash('sha256', $code);
    $owner = hash('sha256', $token);
    $mysql = $db->getAttribute(PDO::ATTR_DRIVER_NAME) === 'mysql';
    $locking = $mysql ? ' FOR UPDATE' : ''; // SQLite is used only by isolated tests.
    for ($attempt = 0; $attempt < 3; $attempt++) {
        try {
            $db->beginTransaction();
            $find = $db->prepare('SELECT code_hash, owner_hash, request_id FROM apprevive_promo_redemptions WHERE owner_hash=? AND request_id=?' . $locking);
            $find->execute([$owner, $request]);
            $receipt = $find->fetch(PDO::FETCH_ASSOC);
            $find->closeCursor();
            if ($receipt) {
                if (!hash_equals($receipt['code_hash'], $hash)) { throw new PromoResult('request_conflict', 409); }
                $db->commit();
                return promo_receipt($hash, $request);
            }
            $find = $db->prepare('SELECT code_hash, owner_hash, request_id FROM apprevive_promo_redemptions WHERE code_hash=?' . $locking);
            $find->execute([$hash]);
            $used = $find->fetch(PDO::FETCH_ASSOC);
            $find->closeCursor();
            if ($used) {
                if (hash_equals($used['owner_hash'], $owner) && hash_equals($used['request_id'], $request)) {
                    $db->commit();
                    return promo_receipt($hash, $request);
                }
                throw new PromoResult('invalid_code', 422);
            }
            // DELETE locks the matching row. Exactly one transaction can win.
            $delete = $db->prepare('DELETE FROM apprevive_promo_codes WHERE code=?');
            $delete->execute([$code]);
            if ($delete->rowCount() !== 1) {
                // Another identical request may have committed while DELETE
                // waited on its row lock. Recover its receipt immediately.
                $retry = $db->prepare('SELECT code_hash FROM apprevive_promo_redemptions WHERE owner_hash=? AND request_id=?' . $locking);
                $retry->execute([$owner, $request]);
                $saved = $retry->fetchColumn();
                $retry->closeCursor();
                if ($saved !== false && hash_equals((string)$saved, $hash)) {
                    $db->commit();
                    return promo_receipt($hash, $request);
                }
                throw new PromoResult('invalid_code', 422);
            }
            $save = $db->prepare('INSERT INTO apprevive_promo_redemptions (code_hash, owner_hash, request_id) VALUES (?,?,?)');
            $save->execute([$hash, $owner, $request]);
            $db->commit(); // Code removal + receipt become visible together.
            return promo_receipt($hash, $request);
        } catch (Throwable $error) {
            if ($db->inTransaction()) { $db->rollBack(); }
            foreach ([$find ?? null, $delete ?? null, $save ?? null, $retry ?? null] as $statement) {
                if ($statement instanceof PDOStatement) { $statement->closeCursor(); }
            }
            $driverCode = $error instanceof PDOException ? (int)($error->errorInfo[1] ?? 0) : 0;
            $lockError = $mysql ? in_array($driverCode, [1205, 1213], true) : in_array($driverCode & 255, [5, 6], true);
            if ($error instanceof PDOException && $lockError && $attempt < 2) {
                usleep(20000 * ($attempt + 1));
                continue;
            }
            if ($error instanceof PDOException && $driverCode === 1062) { throw new PromoResult('invalid_code', 422); }
            throw $error;
        }
    }
    throw new PromoResult('unavailable', 503);
}
