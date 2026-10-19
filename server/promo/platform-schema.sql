-- Apply with the other schema files. Existing balances and orders are preserved.
CREATE TABLE IF NOT EXISTS apprevive_users (
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
 password_hash VARCHAR(255) CHARACTER SET ascii NOT NULL,
 verified TINYINT NOT NULL DEFAULT 0,
 role ENUM('user','admin') NOT NULL DEFAULT 'user',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_sessions (
 token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 expires_at DATETIME NOT NULL,
 KEY user_sessions (user_id), FOREIGN KEY (user_id) REFERENCES apprevive_users(user_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_email_tokens (
 token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 purpose ENUM('verify','reset','apple') NOT NULL,
 email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 expires_at DATETIME NOT NULL,
 KEY user_tokens (user_id), FOREIGN KEY (user_id) REFERENCES apprevive_users(user_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_user_accounts (
 account_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 KEY user_accounts (user_id), FOREIGN KEY (user_id) REFERENCES apprevive_users(user_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_checkouts (
 checkout_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 account_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 quantity INT UNSIGNED NOT NULL,
 amount_kopecks INT UNSIGNED NOT NULL,
 provider_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL UNIQUE,
 confirmation_url VARCHAR(2048) NOT NULL DEFAULT '',
 state ENUM('pending','paid','cancelled','refunded') NOT NULL DEFAULT 'pending',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY user_checkout_request(user_id,request_id), KEY checkout_account(account_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_commissions (
 order_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 partner_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 rate_bps INT UNSIGNED NOT NULL,
 amount_kopecks INT UNSIGNED NOT NULL,
 available_at DATETIME NOT NULL,
 state ENUM('active','void') NOT NULL DEFAULT 'active',
 KEY partner_commissions(partner_id,available_at)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_payouts (
 payout_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 partner_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 amount_kopecks INT UNSIGNED NOT NULL,
 reference VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
 state ENUM('pending','paid','cancelled') NOT NULL DEFAULT 'pending',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY partner_payouts(partner_id,state)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_admin_audit (
 audit_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 action VARCHAR(80) NOT NULL,
 target VARCHAR(128) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_restoration_details (
 account_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 store_id VARCHAR(12) NOT NULL DEFAULT '',
 name VARCHAR(255) NOT NULL DEFAULT '',
 PRIMARY KEY(account_id,request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS apprevive_settings (
 name VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 value TEXT NOT NULL
) ENGINE=InnoDB;

-- Stable partner identity for service users, including users without an Apple ID.
CREATE TABLE IF NOT EXISTS apprevive_user_partners (
 user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 partner_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
 FOREIGN KEY (user_id) REFERENCES apprevive_users(user_id)
) ENGINE=InnoDB;
