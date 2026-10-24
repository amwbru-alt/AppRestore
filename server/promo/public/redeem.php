<?php
declare(strict_types=1);
ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function reply(int $status, array $body): never {
    http_response_code($status);
    echo json_encode($body, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') { header('Allow: POST'); reply(405, ['status' => 'method_not_allowed']); }
if (($_SERVER['HTTPS'] ?? '') !== 'on' && (int)($_SERVER['SERVER_PORT'] ?? 0) !== 443) { reply(400, ['status' => 'https_required']); }
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 4096) { reply(413, ['status' => 'invalid_request']); }
$raw = file_get_contents('php://input', false, null, 0, 4097);
if ($raw === false || strlen($raw) > 4096) { reply(413, ['status' => 'invalid_request']); }
try {
    $body = json_decode($raw, true, 8, JSON_THROW_ON_ERROR);
} catch (JsonException $error) { reply(400, ['status' => 'invalid_request']); }
if (!is_array($body) || !is_string($body['code'] ?? null) || !is_string($body['installation_token'] ?? null) || !is_string($body['request_id'] ?? null)) {
    reply(400, ['status' => 'invalid_request']);
}
try {
    // Layout: site/public_html/apprevive/redeem.php, site/apprevive-promo-private/...
    $private = getenv('APPREVIVE_PROMO_PRIVATE_DIR') ?: dirname(__DIR__, 2) . '/apprevive-promo-private';
    require $private . '/service.php';
    $config = require $private . '/config.php';
    $db = promo_connect($config);
    $result = promo_activate($db, $body['code'], $body['installation_token'], $body['request_id']);
    reply(200, $result);
} catch (PromoResult $error) {
    reply($error->httpStatus, ['status' => $error->status]);
} catch (Throwable $error) {
    // Never return credentials, SQL, code values or filesystem paths to clients.
    error_log('AppRevive promo API failure: ' . get_class($error) . ' [' . $error->getCode() . ']');
    reply(503, ['status' => 'unavailable']);
}
