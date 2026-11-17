# Nguồn mã và thay đổi khi tạo repo sạch

Nguồn là bản tích hợp IoT_WMS đã thống nhất, không lấy lại nguyên archive cũ ghi đè. TV2 cung cấp IOT BE.zip; TV3 cung cấp WMS_TV3_Local.zip gồm backend bảo mật và UI. Firmware/hardware/thông số được phát triển và chốt cùng TV1; có AI hỗ trợ các phần tích hợp/mở rộng/kiểm thử/tài liệu. Phân công V2 mô tả trách nhiệm nhận bàn giao, không đổi nguồn tác giả.

Backend43 file giữ nguyên byte so với bản đang dùng; manifest/patch tại docs/source-review/team-rebase-2026-11-15 và tools/rebuild_team_backend.py --check dùng kiểm chứng. Chỉ tái dựng từ ZIP gốc khi có nhu cầu kiểm nguồn; không cần ZIP gốc để chạy repo.

Bản sạch loại .env/secrets.h, private keys/cert runtime, DB/volume, first-login, cache build, log/chẩn đoán mạng thật, ảnh mockup chờ duyệt, ghi chép lịch sử máy cá nhân. Viết lại tài liệu hiện hành để không còn các ngưỡng cũ đè nhau. Giữ mã chức năng, thông số và sơ đồ có nguồn; không phát sinh lệnh cho thiết bị.

Thay đổi phục vụ đóng gói: Compose name riêng tránh dùng volume demo; browser smoke chọn CHROME_PATH nếu có hoặc Chromium của Playwright; workflow chờ đủ thành phần rồi mới chạy kiểm thử tích hợp; thêm kiểm tra staged file và bàn giao. Không sửa code backend/firmware/frontend chức năng. README/schema mẫu/dữ liệu test không chứa tài khoản thật; các chuỗi password dùng trong unit test là fixture công khai, không được dùng làm mật khẩu triển khai.

Bốn PR là tiếp nhận bản tích hợp đã có tại thời điểm hiện tại, không dựng lại lịch sử phát triển từ đầu. Commit ghi “import/integrate/verify” đúng việc đã làm, giữ ngày thật. Nếu nhóm có repo gốc chứa lịch sử thật, ưu tiên giữ/link lịch sử đó, không thay thế bằng lịch sử diễn tập. Ghi nguồn và AI trong báo cáo.
