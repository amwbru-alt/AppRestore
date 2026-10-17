<?php
// Copy to config.php OUTSIDE public_html. Never put the real config in Git.
return [
    'db_dsn' => 'mysql:host=DB_HOST_FROM_PANEL;port=3306;dbname=DB_NAME_FROM_PANEL;charset=utf8mb4',
    'db_user' => 'DB_USER_FROM_PANEL', // Confirm the complete user name in the Beget panel.
    'db_password' => 'SET_ON_SERVER_ONLY',
    // For an external MySQL server, set the CA file supplied by your host.
    // The database must stay on the same host/private network otherwise.
    'db_ssl_ca' => '/absolute/path/to/database-ca.pem',
    // Only for an RFC1918 IP on a verified private network; not a public host.
    'db_private_network' => false,
];
