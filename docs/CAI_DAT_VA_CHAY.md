# Cài và mở lại trên máy mới

Chỉ thực hiện khi đủ bốn PR. Dự án này có Compose name iot-wms-test-rieng-nhom, tạo volume riêng. Không chạy đồng thời bản demo cũ cùng cổng8443/18883. Bộ nguồn sạch không có tài khoản, dữ liệu, certificate hay credential của bản đang chạy; các ESP cũ vẫn dùng broker/credential cũ cho đến khi TV1 chủ động đổi.

## Lần đầu

Cài Git, Python3.11, Docker Desktop Linux containers; mở Docker Desktop. Laptop và ESP dùng cùng hotspot điện thoại2,4GHz WPA2. Dùng ipconfig lấy IPv4 của Wi-Fi laptop; không lấy IP WSL/Docker/VPN. Ở root repo:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r tools/requirements.txt -r backend/requirements-dev.txt platformio
ipconfig
# Thay LAN_IP_CUA_LAPTOP bằng IPv4 thật, không gõ nguyên placeholder.
./tools/setup-local.ps1 -LanIP LAN_IP_CUA_LAPTOP -MqttPort 18883
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose exec backend python -m scripts.create_user --email admin@example.vn --role Admin --name 'Quan tri demo'
docker compose exec backend python -m scripts.init_hardware
.venv/Scripts/python.exe tools/apply_demo.py --email admin@example.vn
```

create_user hỏi mật khẩu, nhóm tự chọn và lưu riêng. Không nhập lại nếu tài khoản đã tồn tại. init_hardware chỉ tạo hai node thật Registered nếu thiếu, không tạo telemetry giả. apply_demo lưu H8/LOW37,5 và rules rò rỉ20s qua API; tool logout làm các phiên cùng tài khoản cần đăng nhập lại.

Mở https://localhost:8443, kiểm CA nhóm sinh tại deployment/certs/ca.crt. API /api/ready phải trả database/mqtt/broker_admin đều true. Không dùng setInsecure để bỏ xác thực. Nếu trình duyệt chưa tin CA demo, TV1 tự kiểm đúng CA trước khi cài vào Current User; không phát tán khóa riêng. Chỉ cho phép cổng8443/18883 trong phạm vi mạng demo theo chính sách máy, không tắt firewall toàn máy.

Web → Thiết bị & Site → cấp MQTT riêng cho tank/pipe, lưu mật khẩu một lần trong kho riêng. Tắt adapter bơm trước nạp. Chạy configure_firmware, nhập Wi-Fi/IP/18883 và mật khẩu MQTT mới; script tạo secrets.h local. TV1 tự kiểm cổng, tự build/nạp lần lượt đúng role theo firmware/README.md. Với board đã nạp cho bản demo cũ, không đổi broker/CA/mật khẩu chỉ để diễn tập Git: có thể kiểm phần mềm trước, giữ toàn bộ thiết bị ở bản demo.

## Các lần sau và sau restart

Mở hotspot cùng SSID/password2,4GHz và Docker Desktop; laptop vào hotspot. Ở root repo:

```powershell
docker compose up -d
docker compose ps
```

Mở web, đăng nhập bằng tài khoản đã tạo, cắm hai ESP. Không chạy setup-local, create_user, provision hoặc apply_demo mỗi lần mở. Nếu IP laptop thay đổi, cập nhật cấu hình/certificate theo công cụ và TV1 tự nạp; không chỉ bấm Làm mới. Muốn cập nhật source sau git pull dùng docker compose up --build -d rồi kiểm ready.

Tắt demo: đưa TAY, tắt bơm, ngắt adapter bơm; docker compose stop nếu muốn dừng dịch vụ. docker compose down không kèm -v giữ volume; không dùng down -v trên dữ liệu cần giữ. Đổi tên thư mục hoặc Compose project name tạo bộ volume khác, không tự mang dữ liệu cũ theo.

## Xem MySQL

```powershell
docker compose exec mysql mysql -u wms -p wms
```

Nhập MYSQL_PASSWORD từ .env local khi được hỏi; không đưa password vào lệnh/ảnh chụp/commit. Sau đó SHOW TABLES; hoặc SELECT id,device_code,state,online FROM devices; Chỉ truy vấn cần thiết, không xuất users/credentials thật lên repo.
