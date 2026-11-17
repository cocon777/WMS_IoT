# Firmware TV1

Mã thiết bị giữ nguyên từ bản demo hiện tại. Tank tv1-0.3.4, pipe tv1-0.3.2. Cấu hình pin/K/D0 và bảo vệ nằm include/hardware_config.h; config server lưu NVS có thể ghi đè fallback. Đọc docs/THONG_SO_DEMO.md và hardware/README.md trước khi cấp điện.

Tạo secrets.h local bằng tools/configure_firmware.py sau khi có broker/CA và credential riêng. secrets.example.h chỉ để build kiểm tra, không chứa dữ liệu kết nối thật. Không commit secrets.h.

```powershell
.venv/Scripts/python.exe -m platformio run -d firmware -e tank -e pipe
.venv/Scripts/python.exe -m platformio device list
# Tắt adapter bơm. Thay COM_TANK/COM_PIPE bằng cổng đã xác định, không mặc định6/7.
.venv/Scripts/python.exe -m platformio run -d firmware -e tank -t upload --upload-port COM_TANK
.venv/Scripts/python.exe -m platformio run -d firmware -e pipe -t upload --upload-port COM_PIPE
.venv/Scripts/python.exe -m platformio device monitor -p COM_TANK -b 115200
```

TV1 tự nạp; các công cụ bàn giao Git không mở COM/flash board. Nạp lần lượt giúp tránh nhầm role; board cần giữ BOOT khi Connecting tùy mạch auto-reset, không tự chứng minh board hỏng. Ctrl+C thoát Monitor trước nạp. Khi reset, firmware chủ động relay OFF, không phát lại ON; không thay bằng thử tải bơm khi đang nạp.
