<?php
// Local SQLite test harness for the same PHP transaction used by production.
declare(strict_types=1);
require dirname(__DIR__) . '/server/promo/private/service.php';
$db = new PDO('sqlite:' . $argv[1]);
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->exec('PRAGMA busy_timeout=2000');
$mode = $argv[2];
if ($mode === 'init') {
    $db->exec('PRAGMA journal_mode=WAL');
    $db->exec('CREATE TABLE apprevive_promo_codes (code BLOB PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP)');
    $db->exec('CREATE TABLE apprevive_promo_redemptions (code_hash TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, request_id TEXT NOT NULL, activated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(owner_hash,request_id))');
    echo '{}';
} elseif ($mode === 'add') {
    $add = $db->prepare('INSERT INTO apprevive_promo_codes (code) VALUES (?)');
    $add->execute([$argv[3]]);
    echo '{}';
} else {
    try {
        echo json_encode(promo_activate($db, $argv[3], $argv[4], $argv[5]), JSON_THROW_ON_ERROR);
    } catch (PromoResult $error) {
        echo json_encode(['status' => $error->status, 'http' => $error->httpStatus]);
    } catch (Throwable $error) {
        echo json_encode(['status' => 'backend_error', 'type' => get_class($error), 'driver_code' => $error instanceof PDOException ? ($error->errorInfo[1] ?? null) : null]);
    }
}
