# WMS IoT — Hệ thống quản lý cấp nước thông minh

## Giới thiệu

Học phần IoT và ứng dụng xây dựng hệ thống giám sát và quản lý cấp nước sử dụng hai node ESP32: node bồn đo mực nước bằng cảm biến HC-SR04; node đường ống đo lưu lượng bằng YF-S401 và điều khiển bơm qua relay.

Hệ thống hướng đến việc theo dõi dữ liệu trên giao diện web, điều khiển bơm bằng tay hoặc tự động, quản lý thiết bị và cảnh báo các tình huống bất thường trong quá trình cấp nước.

## Cấu trúc thư mục

```text
WMS_IoT/
├── README.md
├── firmware/       # Mã nguồn ESP32
├── backend/        # API, xử lý dữ liệu và quản lý thiết bị
├── frontend/       # Giao diện web
├── database/       # Schema, migration và dữ liệu mẫu
├── deployment/     # Cấu hình triển khai và MQTT broker
├── hardware/       # Sơ đồ đấu nối, linh kiện và ảnh prototype
├── tests/          # Mã và kịch bản kiểm thử
├── docs/           # Thiết kế, báo cáo và slide
├── tools/          # Công cụ hỗ trợ
└── .env.example    # Biến môi trường mẫu, không chứa bí mật thật
```

## Kiến trúc hệ thống

Hệ thống gồm hai node ESP32 và bốn dịch vụ Docker: **Mosquitto** nhận bản tin MQTT, **FastAPI** xử lý nghiệp vụ/API, **MySQL** lưu dữ liệu và **nginx** phục vụ giao diện web qua HTTPS.

```text
ESP32 tank ─┐
            ├─ MQTT/TLS ↔ Mosquitto ↔ FastAPI ↔ MySQL
ESP32 pipe ─┘                           ↕
                              nginx ↔ Web (HTTPS/WSS)
```

Backend quyết định điều khiển AUTO theo mực nước; node ống thực thi lệnh, gửi ACK và duy trì bảo vệ cục bộ. Web cập nhật qua WebSocket, hỗ trợ vai trò Admin/Operator/Viewer, cấu hình thiết bị và cảnh báo. Laptop và hai ESP32 cùng kết nối hotspot điện thoại 2,4 GHz; các dịch vụ chạy local trên laptop.

## Hướng dẫn cài đặt

Cần **Git, Python 3.11, Docker Desktop dùng Linux containers** và hai ESP32 đã đấu nối theo [hardware/README.md](hardware/README.md). Clone repository, mở terminal tại thư mục gốc và bật Docker Desktop:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r tools/requirements.txt -r backend/requirements-dev.txt platformio
ipconfig
# Thay LAN_IP_LAPTOP bằng IPv4 Wi-Fi của laptop trên hotspot.
.\tools\setup-local.ps1 -LanIP LAN_IP_LAPTOP -MqttPort 18883
docker compose up --build -d
docker compose ps
```

Script thiết lập tạo `.env` và chứng chỉ TLS cục bộ. Kiểm tra `https://localhost:8443/api/ready` trả trạng thái `ready`; thiết lập tin cậy CA demo theo [hướng dẫn cài đặt chi tiết](docs/CAI_DAT_VA_CHAY.md). Không đưa `.env`, `secrets.h`, mật khẩu hoặc khóa riêng lên Git.

## Hướng dẫn chạy

**Lần đầu trên database mới**, tạo tài khoản quản trị, hai bản ghi thiết bị và áp cấu hình demo:

```powershell
docker compose exec backend python -m scripts.create_user --email admin@example.vn --role Admin --name "Quan tri demo"
docker compose exec backend python -m scripts.init_hardware
.venv\Scripts\python.exe tools/apply_demo.py --email admin@example.vn
```

Tự chọn mật khẩu khi được hỏi. Mở **https://localhost:8443**, đăng nhập → **Thiết bị & Site → Danh sách node → Cấp MQTT** riêng cho từng node. Chạy công cụ sau để tạo cấu hình kết nối local, rồi build/nạp đúng vai trò tank và pipe theo [firmware/README.md](firmware/README.md):

```powershell
.venv\Scripts\python.exe tools/configure_firmware.py
```

Nhập Wi-Fi, IPv4 laptop, cổng MQTT TLS **18883** và hai mật khẩu MQTT vừa cấp. Giữ adapter bơm ngắt điện trong lúc nạp. Khi hai node online, có mẫu mới và cấu hình **Đã áp dụng**, kiểm tra nước rồi cấp adapter, thử **Bật 3 giây** trước khi chạy TAY/AUTO. Hồ sơ demo: đầy **8 cm**, thấp **3 cm**; xem [thông số demo](docs/THONG_SO_DEMO.md).

**Các lần sau:** bật cùng hotspot và Docker Desktop, chạy tại root repository:

```powershell
docker compose up -d
docker compose ps
```

Mở web, đăng nhập và cấp nguồn ESP32; không cần tạo lại tài khoản, cấp MQTT hoặc nạp firmware mỗi lần. Khi đổi IP/mạng, cập nhật cấu hình kết nối theo hướng dẫn chi tiết. Trước khi nghỉ: chuyển TAY, tắt bơm, ngắt adapter rồi chạy `docker compose stop`; giữ Docker volumes để bảo toàn dữ liệu.
