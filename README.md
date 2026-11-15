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

## Hướng dẫn cài đặt

## Hướng dẫn chạy
