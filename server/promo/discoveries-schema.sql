-- Anonymous app metadata candidates. No Apple ID, device ID or user linkage.
CREATE TABLE IF NOT EXISTS apprevive_catalog_discoveries (
 store_id VARCHAR(12) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 bundle_id VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 name VARCHAR(255) NOT NULL,
 source ENUM('apple_history','device_offloaded') NOT NULL,
 state ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 reviewed_at DATETIME NULL,
 KEY discovery_review(state,store_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
