-- Apply after schema.sql and accounts-schema.sql. Never clear with client data.
CREATE TABLE IF NOT EXISTS apprevive_partners (
  account_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  referral_code CHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (account_id) REFERENCES apprevive_accounts(account_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_referrals (
  buyer_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  partner_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY partner_buyers (partner_id),
  FOREIGN KEY (buyer_id) REFERENCES apprevive_accounts(account_id),
  FOREIGN KEY (partner_id) REFERENCES apprevive_partners(account_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_orders (
  order_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  payment_reference VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
  buyer_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  partner_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  quantity INT UNSIGNED NOT NULL,
  amount_kopecks INT UNSIGNED NOT NULL,
  state ENUM('paid','refunded') NOT NULL DEFAULT 'paid',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY partner_orders (partner_id,state),
  FOREIGN KEY (buyer_id) REFERENCES apprevive_accounts(account_id),
  FOREIGN KEY (partner_id) REFERENCES apprevive_partners(account_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS apprevive_order_codes (
  code_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  order_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  KEY order_codes (order_id),
  FOREIGN KEY (order_id) REFERENCES apprevive_orders(order_id)
) ENGINE=InnoDB;
