# Kiểm thử

Ở root repo:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt -r tools/requirements.txt
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe tools/rebuild_team_backend.py --check
./tools/test-control.ps1
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe tools/smoke_frontend.py
```

test-control.ps1 cần g++ trong PATH (hoặc gọi compiler PlatformIO mingw đã cài). Test Python dùng DB tạm/fake broker, browser smoke dùng API/WS thật trên SQLite với MQTT giả và không mở cổng COM. Kết quả sinh tại tests/results, bịignore; chỉ chọn kết quả đã ẩn thông tin riêng để nộp, không commit nguyên log máy demo. Kiểm vật lý/Docker thật theo docs/TEST_PLAN.md. Test build firmware chỉ compile; nạp do TV1 tự làm.
