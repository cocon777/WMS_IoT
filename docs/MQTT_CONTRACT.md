# Hợp đồng MQTT

| Topic | Chiều | QoS | Retain |
| --- | --- | --- | --- |
| wms/{device_code}/telemetry | node→backend | 1 mặc định | false |
| wms/{device_code}/status | node→backend | 1 | true |
| wms/{device_code}/ack | node→backend | 1 | false |
| wms/{device_code}/cmd | backend→pipe | 1 | false |
| wms/{device_code}/config | backend→node | 1 | true |

Username=device_code, mật khẩu khác nhau cho tank và pipe. Device payload `device_id` là chuỗi code, REST device_id là số DB. `boot_id` dài≤16, seq không âm, timestamp ISO8601 UTC có Z. Backend bỏ unknown fields như unit. Telemetry phải có các trường theo loại, không gửi lỗi cảm biến thành số hợp lệ giả.

```json
{"device_id":"wms-tank-01","boot_id":"0123456789abcdef","seq":1,"ts":"2026-11-12T01:00:00.123Z","distance_cm":12.5,"level_pct":50,"rssi":-60,"unit":{"distance":"cm","level":"%"}}
```

```json
{"device_id":"wms-pipe-01","boot_id":"fedcba9876543210","seq":1,"ts":"2026-11-12T01:00:00.123Z","flow_lpm":0,"flow_total_l":0,"pump_on":false,"rssi":-60,"unit":{"flow":"L/min","total":"L"}}
```

```json
{"status":"online","fw_version":"tv1-0.3.4","free_heap":150000,"config_version":3}
```

LWT `{"status":"offline"}` retained; status online lần kết nối và heartbeat30s. Backend bỏ retained online cũ khi subscribe; đợi heartbeat mới. Offline khi LWT hoặc quá90s thiếu last_seen, watcher có chu kỳ nên không hứa đúng tuyệt đối90.000s.

```json
{"cmd_id":"uuid-from-backend","action":"pump","value":"on","duration_s":3,"issued_at":"2026-11-12T01:00:00Z"}
```

```json
{"cmd_id":"uuid-from-backend","result":"ok","reason":null,"ts":"2026-11-12T01:00:00.456Z"}
```

Firmware không publish trong callback MQTT; nhớ16 cmd_id ở NVS, TTL10s. Khi phát hiện trùng, trả lại kết quả gốc, không điều khiển lại. Lệnh off không cần duration. Backend timeout5s, ACK muộn vẫn cập nhật. Reason fail thường có calibration_required/expired/over_limit/busy/no_flow_latched_send_off/nvs_failure.

```json
{"version":3,"sample_interval_s":1,"tank_height_cm":8,"low_pct":37.5,"high_pct":100,"pump_max_run_s":60,"auto_mode":false,"leak_flow_lpm":0.3,"leak_minutes":1}
```

Config phẳng trên MQTT (REST GET có object config lồng). Firmware dùng version/sample/height/threshold/maxRun; auto/leak do backend. Khi version tăng lưu NVS và báo applied. Từ firmware tv1-0.2.0, `tank_height_cm=H` là chiều cao cột nước ở vạch đầy, đúng với phép đổi %→cm backend; `SENSOR_TO_BOTTOM_CM=D0` lưu cục bộ. Cấu hình hiện hành H8cm, D0=16,5cm, LOW37,5%=3cm, HIGH100%; ví dụ version3 không phải xác nhận mọi board đã applied3. Mức %=clamp(100×(D0−distance)/H,0,100). Không thêm trường full vào API. Cần PUT/publish hồ sơ mới khi nâng firmware từ cách ánh xạ cũ. Firmware giới hạn cứng ON60s dù config backend có thể cho phép120s.

Backend ts tolerance±300s, payload≤2048 bytes, 100 messages/10s/device tính cả các topic. Buffer firmware tối đa180 mẫu, TTL240s, flush≤2/s. Tổng flow tính từ boot, chưa persist.
