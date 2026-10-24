-- Apply AFTER schema.sql. Compatible with MySQL 5.7 / Percona.
-- Keep these tables when clearing client data or deploying a new version.
CREATE TABLE IF NOT EXISTS apprevive_accounts (
    account_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    credits INT UNSIGNED NOT NULL DEFAULT 1,
    installations INT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_restorations (
    account_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    state ENUM('reserved','completed','failed') NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, request_id),
    KEY account_state (account_id, state),
    FOREIGN KEY (account_id) REFERENCES apprevive_accounts(account_id)
) ENGINE=InnoDB;
