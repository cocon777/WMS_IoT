# Thông số demo đã chốt

| Thông số | Giá trị |
|---|---|
| Mốc rỗng D0 |16,5 cm từ cảm biến xuống đáy |
| Mức đầy H |8 cm quy đổi; khoảng cách đầy8,5 cm |
| Mức thấp |Dưới3 cm =37,5% trong10 giây; reset trên3,4 cm |
| Flow YF-S401 |8157,0552 xung/lít |
| Chế độ ban đầu |TAY, không tự chạy khi cấp nguồn |
| Tắt bơm |Đầy≥100%, trần60 giây, các bảo vệ mất dữ liệu/không dòng |
| Rò rỉ bồn |Bơm OFF ổn định5s, cửa sổ20s, giảm≥0,6cm và tốc độ>1cm/phút; mẫu mới và không hở quá5s |
| Nguồn mạng |Laptop và cả hai ESP cùng hotspot2,4GHz WPA2; Docker local |

Firmware tank tv1-0.3.4, pipe tv1-0.3.2; không đổi thuật toán khi đóng gói Git. h=16,5−distance_cm; %=clamp(100h/8,0,100). Đây là chiều cao quy đổi theo mốc TV1 chốt, không có chứng nhận độ chính xác tuyệt đối bằng thước. Lọc median/EMA giảm dao động, không khắc phục được cảm biến đặt sai hoặc echo sai kéo dài.

Cấu hình server lưu trong MySQL và publish config retained xuống node; node lưu NVS. Chỉ nạp lại firmware không bảo đảm ghi đè cấu hình NVS cũ. Trên máy mới cần khởi tạo inventory rồi áp hồ sơ deployment/demo và kiểm server/node applied khớp. Phiên bản tăng theo từng DB/node, không ép version cũ của máy demo.

Vòi đáy bình nhận xả ra ngoài, không đi qua YF-S401 đầu vào: demo nghi rò rỉ dựa trên mực giảm của tank; không đòi inlet flow>0. Vòi có thể để lại3–4 cm, chưa đủ LOW<3cm; muốn thử AUTO phải lấy thêm nước khi bơm đã OFF xuống khoảng2,5–2,8 cm. Chu kỳ2,8→8cm ước khoảng33s theo số đo cũ800mL/7cm/44,48s, không phải thời gian nghiệm thu mới.

Đo flow TV1 đã cung cấp:3404xung/440mL,4742/580mL,5150/610mL; K gộp=13296/1,630=8157,0552. Kiểm tra độc lập6378xung/800mL/44,48s cho781,9mL, sai số−2,26%. Không sửa các số đo gốc thành số đo mới tại vạch8cm.
