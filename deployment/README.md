# Triển khai TV3

Compose ở root, gồm4 dịch vụ mysql/mosquitto/backend/frontend. Broker TLS8883 nội bộ, host18883 theo hướng dẫn; nginxHTTPS8443. Dynamic Security dùng tài khoản admin tách tài khoản backend đọc/ghi dữ liệu. Không anonymous, không public API8000/MySQL3306. Khởi tạo theo docs/CAI_DAT_VA_CHAY.md. deployment/certs và runtime sinh trên máy, không đưa vào Git. Hồ sơ demo hiện hành trong demo/, không chứa credential.
