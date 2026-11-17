# WebSocket `/ws` (hợp đồng cho frontend)

Một kết nối cho cả ứng dụng; backend chỉ gửi những gì người dùng được phép xem (theo vai trò và thiết bị được gán).
Hệ thống có hai node (bồn và ống) trong cùng một site: dashboard nhận sự kiện của cả hai và ghép theo `site_id`.
Không có phát lại: sau khi (kết nối lại) hãy nạp trạng thái bằng REST (`/api/devices`, `.../telemetry/latest`, `/api/alerts?state=open`).

## Kết nối và xác thực

1. Mở `wss://<host>/ws` (dev: `ws://localhost:8000/ws`).
2. Trình duyệt: gửi **ngay** thông điệp đầu tiên (trong 5 giây) `{"type":"auth","token":"<JWT từ /api/auth/login>"}`.
   Không đưa token lên URL (lộ trong log). Máy khách không phải trình duyệt có thể dùng header `Authorization: Bearer <JWT>`.
3. Nhận `ready`, từ đó nhận sự kiện.

JWT sống 30 phút: khi hết hạn máy chủ đóng kết nối bằng mã `4401`; đăng nhập lại rồi kết nối lại.
Đăng xuất, đổi mật khẩu, đổi vai trò hoặc khóa tài khoản cũng đóng kết nối (kiểm tra mỗi 30 giây).
Thay đổi thiết bị được gán có hiệu lực trên kết nối đang mở trong tối đa 30 giây.

## Thông điệp từ máy chủ

Mọi thông điệp có dạng `{"event": "...", "data": {...}, "sent_at": "2026-11-01T09:00:05.123Z"}` (UTC).

| event | Khi nào | Ai nhận | `data` chính |
| --- | --- | --- | --- |
| `ready` | Sau xác thực | mọi vai trò | `user_id`, `role`, `expires_at`, `events` (được nhận), `device_ids` (`null` = mọi thiết bị) |
| `telemetry` | Mỗi mẫu đã lưu | mọi vai trò | `device_id`, `device_code`, `type` (`tank`/`pipe`), `site_id`, `state`, `ts`, `received_at`; **node bồn:** `distance_cm`, `level_pct`; **node ống:** `flow_lpm`, `flow_total_l`, `pump_on` (trường không áp dụng cho loại node là `null`) |
| `device_state` | Online/offline, đổi trạng thái vòng đời, Fault | mọi vai trò | `device_id`, `device_code`, `type`, `site_id`, `state`, `online`, `fw_version` |
| `alert` | Cảnh báo mở / ack / đóng | mọi vai trò | `alert_id`, `device_id`, `type`, `severity`, `value`, `state`, `opened_at`, `acked_at`, `closed_at` |
| `command_result` | Lệnh bơm có kết quả | Admin, Operator | `device_id`, `cmd_id`, `status` (`ok`/`fail`/`timeout`), `reason`, `acked_at` |
| `config` | Cấu hình được lưu | Admin, Operator | `device_id`, `version`, `config`, `sync_status` |
| `config_applied` | Thiết bị báo đã áp dụng cấu hình | Admin, Operator | `device_id`, `applied_version` |
| `subscribed`, `pong`, `error` | Phản hồi thông điệp của máy khách | | `error`: `code`, `message` |

`command_result` với `status: "sent"` không được phát: giao diện tự hiển thị trạng thái "đang chờ" sau khi gọi `POST .../commands`.

## Thông điệp từ máy khách

- `{"type":"subscribe","device_ids":[1,2],"events":["telemetry","alert"]}`: chỉ nhận tập con (cả hai trường đều tùy chọn;
  `device_ids` phải nằm trong phạm vi được gán, nếu không nhận `error` `forbidden_device`). Gửi `{"type":"subscribe"}` để bỏ bộ lọc.
  Trang chi tiết thiết bị nên subscribe riêng thiết bị đó.
- `{"type":"ping"}` nhận `pong` (kiểm tra kết nối sống; trình duyệt không thấy ping của giao thức).
- Tối đa 4 KB mỗi thông điệp và 20 thông điệp / 10 giây.

## Mã đóng kết nối

| Mã | Ý nghĩa | Xử lý |
| --- | --- | --- |
| `4401` | Chưa xác thực, token sai/hết hạn/bị thu hồi | Đăng nhập lại |
| `1008` | Origin không được phép, hoặc gửi quá nhanh | Sửa cấu hình/mã nguồn |
| `1009` | Thông điệp quá lớn | |
| `1013` | Quá tải, quá số kết nối (5/người, 200 tổng), hoặc máy khách nhận quá chậm | Kết nối lại sau vài giây (backoff), rồi nạp lại bằng REST |

Gợi ý kết nối lại: backoff 1 s, 2 s, 4 s ... tối đa 30 s, có jitter; sau khi kết nối lại luôn nạp trạng thái bằng REST.

## Đo độ trễ (báo cáo mục 11)

`GET /api/metrics/latency` (Admin) trả trung bình, p95 và max (ms) trên 2000 mẫu gần nhất:
`device_to_backend_ms` (`received_at - ts`, `ts` có độ phân giải 1 giây nên sai số tới ~1 s),
`backend_to_push_ms` (`sent_at - received_at`, phía server), `end_to_push_ms` (`sent_at - ts`).
Độ trễ tới trình duyệt = thời điểm trình duyệt nhận − `data.ts` (cần đồng hồ máy khách đúng).
`DELETE /api/metrics/latency` xóa bộ đếm trước mỗi lần đo.
