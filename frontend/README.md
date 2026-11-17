# Giao diện TV4 tiếp nhận từ thiết kế TV3

Giữ phong cách TV3, bố cục compact đã duyệt; compact-ui.js và css/compact.css phối hợp app.js/management.js/tv3-integration.js. Web dùng REST/WS qua nginx cùng origin; không mở index.html bằng file:// để chạy hệ thống. JWT ở RAM; backend kiểm quyền thật. Site2 là mô phỏng và không thay số đo hai ESP. Chạy tools/smoke_frontend.py theo tests/README.md để kiểm các trang/refresh/recovery/layout.
