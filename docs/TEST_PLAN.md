# Kịch bản nghiệm thu trên bản cuối

| Luồng | Thực hiện và quan sát |
|---|---|
| TAY LOW→đầy |Nguồn đủ nước, bình nhận<3cm trong10s; cảnh báo LOW, không tự bật; bấm Bơm tới đầy, ACK; mức≥8cm quy đổi gửiOFF, relay/pump thực dừng |
| AUTO |Đưa bình nhận xuống<3cm khiOFF, bậtAUTO; LOW đủ10s tựON; đầy tựOFF; không lặpON liên tục cùng đợt |
| Rò rỉ vòi |ĐưaTAY, nước khoảng7cm, bơmOFF; mở van giảm>0,6cm/20s, tốc độ>1cm/phút; sau settle và đủ cửa sổ có LEAK_SUSPECT; khóa vòi, theo dõi đóng; không xem là kết luận rò rỉ chắc chắn |
| Khôi phục mạng |Bơm được giám sát; thử mất MQTT/Wi-Fi có chủ đích, đo thời gian guardOFF/reconnect; phân biệt sample cũ với online; ghi boot_id/reset reason nếu nghi reset |
| Phân quyền |Viewer không bật bơm/sửa config, Operator chỉ site được gán; API chặn thật, không chỉ ẩn nút |
| Thu hồi |Credential node bị revoke không kết nối/publish được; backend chặn thiết bị khôngActive |
| Site2 |Chạy tools/simulate_site2.py bằng credential riêng, gắn MÔ PHỎNG; thử ACL chéo, không thay số đo thật |
| UI |Làm mới có phản hồi thành công/lỗi, WS reconnect, lịch sử/CSV, layout desktop/mobile |

TV1 tổng hợp kết quả, mỗi người nộp log/ảnh của phần mình. Ngắt adapter bơm trước thao tác dây/nạp/mở cổng có thể reset board; không thử bơm cạn. Không ghi các bước chưa chạy là PASS.
