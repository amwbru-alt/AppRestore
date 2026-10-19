CREATE TABLE IF NOT EXISTS apprevive_catalog_groups (
  group_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  icon_url VARCHAR(2048) NOT NULL DEFAULT '',
  enabled TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS apprevive_catalog_variants (
  store_id VARCHAR(12) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  group_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  KEY group_variants (group_id),
  FOREIGN KEY (group_id) REFERENCES apprevive_catalog_groups(group_id)
) ENGINE=InnoDB;
