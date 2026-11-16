# Bảo mật và vận hành bản demo

## Ranh giới tin cậy

Thiết bị có credential riêng → MQTT TLS → Mosquitto → FastAPI → MySQL. Người dùng → HTTPS/WSS nginx → JWT/API. MySQL và API chỉ ở mạng Docker. Máy host, Docker admin và firmware chứa secrets là thành phần được tin cậy; ai đọc được file local có thể lấy credential. Đây là nguyên mẫu LAN, chưa phải hệ thống cấp nước vận hành công nghiệp.

## Các biện pháp đã triển khai

| Nguy cơ | Biện pháp | Giới hạn cần hiểu |
|---|---|---|
| Nghe lén/mạo danh broker | TLS MQTT, CA pin trong ESP32, SAN IP/hostname; HTTPS nginx | CA demo riêng; đồng hồ NTP phải đúng; đổi IP cần chứng chỉ đúng |
| Node đọc/lệnh chéo | Role riêng `wms-device-<code>`, topic cụ thể `wms/<code>/…`, subscribeLiteral; mặc định publish/receive/subscribe deny | ESP32 bị lấy credential vẫn có thể giả dữ liệu của chính node đó |
| Backend data quản trị broker | Tách username/password data và dynsec; data chỉ `wms/#` | Process backend giữ cả hai secrets để onboarding; máy host vẫn là quyền cao |
| Chiếm tài khoản ứng dụng | bcrypt, JWT hạn dùng, token_version khi logout/đổi pass, khóa tạm đăng nhập sai | Không có MFA, chưa có distributed rate limiter trước nginx |
| Vượt quyền | Admin/Operator/Viewer, UserDevice scope kiểm tra tại API và WS | Ẩn nút UI chỉ hỗ trợ trải nghiệm, server mới là kiểm soát bắt buộc |
| Phát lại/lệnh trễ | seq+boot_id unique; TTL cmd, dedupe cmd_id ở NVS; config version | QoS1 không tự đem lại exactly-once |
| Payload lỗi/quá nhanh | validate schema, timestamp, kích thước, rate theo node | Không thay cho giới hạn lưu lượng tổng tại firewall/broker |
| Chèn mã trên web | Dữ liệu người dùng đi qua textContent, token chỉ trong RAM, CSV escape | Swagger dùng tài nguyên riêng; chưa có CSP chặt cho mọi trang |
| Mất liên lạc bơm | OFF hạn chạy/no-flow/mạng tại pipe, stale tank guard ở BE | BE chết khi MQTT còn sống: chờ local timeout; không có source-level sensor |
| Lộ secrets qua Git | .gitignore, ZIP loại trừ .env/secrets/certs/runtime | Kiểm tra staged files; secrets đã lộ phải rotate, xóa file mới không đủ |

## Khóa và thu hồi

Provision chỉ hiện mật khẩu một lần, backend lưu hash. `Maintenance` gọi disableClient trước khi ghi DB để ngắt kết nối broker; trở về Active bật credential. `Decommissioned` xóa client MQTT, đánh dấu revoked, không phục hồi cùng vòng đời. Làm sau phần demo nước. Nếu broker lỗi thì API báo lỗi, không giả vờ đã khóa. Nếu DB commit lỗi sau broker thay đổi, log nêu cần đối soát.

Khi đổi secret data/admin hoặc password MySQL, không chỉ sửa `.env`: cập nhật tài khoản tương ứng trong dịch vụ đang chạy, sửa `.env`, restart và kiểm tra ready. Nếu mất credential node đã cấp, không có API đọc lại mật khẩu; dùng quy trình thu hồi và đăng ký node mới có mã mới, cập nhật DEVICE_ID. Không can thiệp DB để giả Registered.

## Backup và phục hồi

Trước thay đổi triển khai: dừng bơm, chuyển TAY, export CSV cần giữ. Backup **cả MySQL và volume mqtt_data** cùng mốc, vì bảng credential hash không thể tái tạo mật khẩu broker. Lưu `.env`, CA/server cert+key riêng ở nơi không chia sẻ, không trong repo. MySQL dump cần routines/events; giữ migration001–004 để hiểu schema. Volume broker chứa hash/ACL và retained data cũng là dữ liệu nhạy cảm.

TV3 có thể dùng Docker Desktop Volumes export khi đã `docker compose stop` cho snapshot nhất quán; import vào project thử riêng để nghiệm thu. Không ghi đè volume demo để thử restore. Sau restore kiểm tra health/ready, login, config version, heartbeat và API query trước khi cấp nguồn bơm. Chưa có chứng cứ restore thành công nếu chưa lưu log thao tác đó.

## Tài liệu nguồn

[Mosquitto Dynamic Security](https://mosquitto.org/documentation/dynamic-security/) mô tả role/ACL, mặc định và disable/delete client. `%u` trong dynsec chỉ được thêm từ [Mosquitto2.1](https://mosquitto.org/blog/2026/01/version-2-1-0-released/); bản nhóm giữ image2.0.22 và Python mở rộng template thành topic cụ thể, đã bổ sung test chống tái lỗi. [Docker Desktop Windows](https://docs.docker.com/desktop/setup/install/windows-install/) hướng dẫn WSL2 và tùy chọn cài/data-root. Quyết định demo theo mạch TV1 đã xác nhận.
