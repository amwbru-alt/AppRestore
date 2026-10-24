<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/service.php';
$config = require __DIR__ . '/config.php';
$db = promo_connect($config);
$mode = $argv[1] ?? '';
if ($mode === 'generate') {
    $count = filter_var($argv[2] ?? '1', FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 1000]]);
    if ($count === false) { fwrite(STDERR, "Count must be 1..1000\n"); exit(2); }
    for ($i = 0; $i < $count; $i++) {
        $code = 'RV-' . strtoupper(bin2hex(random_bytes(12)));
        $insert = $db->prepare('INSERT INTO apprevive_promo_codes (code) VALUES (?)');
        $insert->execute([$code]);
        echo $code . PHP_EOL;
    }
} elseif ($mode === 'import') {
    $file = $argv[2] ?? '';
    if (!is_file($file)) { fwrite(STDERR, "Specify a local UTF-8 text file\n"); exit(2); }
    $text = file_get_contents($file);
    if ($text === false || strlen($text) > 2 * 1024 * 1024) { exit(2); }
    $text = preg_replace('/\A\xEF\xBB\xBF/', '', $text);
    $count = 0;
    foreach (preg_split('/\r\n|\n|\r/', $text) as $line) {
        $code = trim($line);
        if ($code === '' || strlen($code) > 256) { continue; }
        $used = $db->prepare('SELECT 1 FROM apprevive_promo_redemptions WHERE code_hash=?');
        $used->execute([hash('sha256', $code)]);
        if ($used->fetchColumn()) { continue; }
        $insert = $db->prepare('INSERT IGNORE INTO apprevive_promo_codes (code) VALUES (?)');
        $insert->execute([$code]);
        $count += $insert->rowCount();
    }
    echo 'Imported: ' . $count . PHP_EOL;
} else {
    fwrite(STDERR, "Usage: php manage.php generate [count] | import /path/codes.txt\n"); exit(2);
}
