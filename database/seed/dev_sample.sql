-- DỮ LIỆU MẪU CHỈ DÙNG KHI PHÁT TRIỂN/DEMO. Không chứa thông tin thật và KHÔNG chứa tài khoản người dùng
-- (mật khẩu không được commit): tạo tài khoản bằng `python -m scripts.create_user` (xem database/README.md).
-- Idempotent: chạy lại không nhân đôi dữ liệu. Nạp: mysql -u<admin> -p wms < database/seed/dev_sample.sql
-- (Dùng SQLite thì chạy `python -m scripts.seed_dev` thay cho file này.)

INSERT IGNORE INTO sites (name, description) VALUES ('Nhà mẫu', 'Địa điểm demo: một node bồn và một node ống');

-- Hai node ở trạng thái Active để thử ngay. Muốn demo luồng Registered -> Provisioned -> Active thì bỏ qua đoạn này.
INSERT IGNORE INTO devices (device_code, name, `type`, site_id, state, hw_version, fw_version, online)
SELECT 'wms-tank-01', 'Node bồn (mực nước, còi)', 'tank', s.id, 'Active', 'v1', '0.1.0', 0
FROM sites s WHERE s.name = 'Nhà mẫu';

INSERT IGNORE INTO devices (device_code, name, `type`, site_id, state, hw_version, fw_version, online)
SELECT 'wms-pipe-01', 'Node ống (lưu lượng, bơm)', 'pipe', s.id, 'Active', 'v1', '0.1.0', 0
FROM sites s WHERE s.name = 'Nhà mẫu';

-- Cấu hình mặc định (khớp khung mục 4.2 và device_params.DEFAULTS), mỗi node một bản
INSERT IGNORE INTO device_configs (device_id, `key`, `value`, version)
SELECT d.id, c.k, c.v, 1
FROM devices d
CROSS JOIN (
  SELECT 'sample_interval_s' AS k, '5' AS v
  UNION ALL SELECT 'tank_height_cm', '25'
  UNION ALL SELECT 'low_pct', '20'
  UNION ALL SELECT 'high_pct', '90'
  UNION ALL SELECT 'pump_max_run_s', '120'
  UNION ALL SELECT 'auto_mode', 'true'
  UNION ALL SELECT 'leak_flow_lpm', '0.3'
  UNION ALL SELECT 'leak_minutes', '10'
) c
WHERE d.device_code IN ('wms-tank-01', 'wms-pipe-01');

-- 24 giờ telemetry giả (288 mẫu, cách nhau 5 phút). Node bồn: mực nước dao động 25-85%.
INSERT IGNORE INTO telemetry
  (device_id, boot_id, seq, ts, received_at, distance_cm, level_pct, flow_lpm, flow_total_l, pump_on, rssi)
WITH RECURSIVE n (i) AS (
  SELECT 0
  UNION ALL
  SELECT i + 1 FROM n WHERE i < 287
)
SELECT d.id, 'seed', n.i,
       UTC_TIMESTAMP(3) - INTERVAL (287 - n.i) * 5 MINUTE,
       UTC_TIMESTAMP(3) - INTERVAL (287 - n.i) * 5 MINUTE,
       ROUND(25 * (1 - (55 + 30 * SIN(n.i / 30)) / 100), 1),
       ROUND(55 + 30 * SIN(n.i / 30), 1),
       NULL, NULL, NULL,
       -60
FROM n
JOIN devices d ON d.device_code = 'wms-tank-01';

-- Node ống: bơm chạy 8 mẫu liên tiếp mỗi giờ (lưu lượng 3,2 L/phút), còn lại tắt và không có dòng chảy.
INSERT IGNORE INTO telemetry
  (device_id, boot_id, seq, ts, received_at, distance_cm, level_pct, flow_lpm, flow_total_l, pump_on, rssi)
WITH RECURSIVE n (i) AS (
  SELECT 0
  UNION ALL
  SELECT i + 1 FROM n WHERE i < 287
)
SELECT d.id, 'seed', n.i,
       UTC_TIMESTAMP(3) - INTERVAL (287 - n.i) * 5 MINUTE,
       UTC_TIMESTAMP(3) - INTERVAL (287 - n.i) * 5 MINUTE,
       NULL, NULL,
       IF(MOD(n.i, 60) BETWEEN 40 AND 47, 3.2, 0),
       ROUND(n.i * 0.8, 1),
       IF(MOD(n.i, 60) BETWEEN 40 AND 47, 1, 0),
       -58
FROM n
JOIN devices d ON d.device_code = 'wms-pipe-01';
