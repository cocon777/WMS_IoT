-- Hệ thống 2 node: node bồn (tank) đo mực nước; node ống (pipe) đo lưu lượng và điều khiển bơm.
--  - devices.type (tank | pipe)
--  - telemetry: các trường không áp dụng cho loại node thì NULL; bỏ cột fault (node không còn gửi)
--  - cảnh báo PUMP_NO_FLOW đổi thành PUMP_NO_RISE; cấu hình dry_run_s bị bỏ (thay bằng leak_flow_lpm, leak_minutes)
-- Thiết bị đã có từ hệ thống 1 node được gán type='tank' (giá trị mặc định); Admin đổi lại nếu cần.
-- Lưu ý: ALTER TABLE của MySQL không idempotent; file này chỉ chạy một lần (xem schema_migrations).
ALTER TABLE devices
  ADD COLUMN `type` VARCHAR(8) NOT NULL DEFAULT 'tank' AFTER name,
  ADD CONSTRAINT ck_devices_type CHECK (`type` IN ('tank', 'pipe'));

ALTER TABLE telemetry
  MODIFY COLUMN distance_cm FLOAT NULL,
  MODIFY COLUMN level_pct FLOAT NULL,
  MODIFY COLUMN flow_lpm FLOAT NULL,
  MODIFY COLUMN flow_total_l DOUBLE NULL,
  MODIFY COLUMN pump_on TINYINT(1) NULL,
  DROP COLUMN fault;

ALTER TABLE alert_rules DROP CHECK ck_alert_rules_type;
ALTER TABLE alerts DROP CHECK ck_alerts_type;
UPDATE alert_rules SET type = 'PUMP_NO_RISE' WHERE type = 'PUMP_NO_FLOW';
UPDATE alerts SET type = 'PUMP_NO_RISE' WHERE type = 'PUMP_NO_FLOW';
ALTER TABLE alert_rules
  ADD CONSTRAINT ck_alert_rules_type CHECK (type IN ('LOW_LEVEL', 'HIGH_LEVEL', 'LEAK_SUSPECT', 'PUMP_NO_RISE', 'DEVICE_OFFLINE'));
ALTER TABLE alerts
  ADD CONSTRAINT ck_alerts_type CHECK (type IN ('LOW_LEVEL', 'HIGH_LEVEL', 'LEAK_SUSPECT', 'PUMP_NO_RISE', 'DEVICE_OFFLINE'));

DELETE FROM device_configs WHERE `key` = 'dry_run_s';

INSERT IGNORE INTO schema_migrations (version) VALUES ('004_two_node');
