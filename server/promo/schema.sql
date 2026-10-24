-- Import into the selected MySQL/MariaDB database. Existing tables are untouched.
CREATE TABLE IF NOT EXISTS apprevive_promo_codes (
    code VARBINARY(256) NOT NULL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Receipts contain a hash, not the original code. Keep them for safe retries.
CREATE TABLE IF NOT EXISTS apprevive_promo_redemptions (
    code_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    owner_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    activated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY owner_request (owner_hash, request_id)
) ENGINE=InnoDB;
