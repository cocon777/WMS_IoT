# Phần cứng hai node

Thông số hiện hành tại docs/THONG_SO_DEMO.md. Không còi; relay active HIGH; flyback diode đã được TV1 xác nhận lắp.

## Đấu dây


| Node | Tín hiệu | ESP32 | Nguồn và xử lý mức điện áp |
| --- | --- | --- | --- |
| Bồn | HC-SR04 TRIG | GPIO5 | VCC từ VIN/5V của USB, GND về GND node bồn |
| Bồn | HC-SR04 ECHO | GPIO18 | ECHO → 10k → điểm GPIO18 → 20k → GND |
| Ống | YF-S401 signal vàng | GPIO27 | Signal → 10k → điểm GPIO27 → 20k → GND; đỏ 5V, đen GND |
| Ống | Relay IN | GPIO26 | HIGH bật, LOW tắt theo bring-up TV1; relay VCC 5V, GND cùng ESP32 ống |
| Bơm | Nguồn + | Relay COM | Adapter 5V/2A → COM; NO → cực + bơm |
| Bơm | Nguồn − | Cực − bơm | Cực − bơm về cực − adapter; dòng bơm không đi qua breadboard |

Giữ hai node độc lập, mỗi ESP32 một USB. Với mạch tiếp điểm relay COM/NO cách ly như HTML, **không cần nối âm adapter bơm với GND ESP32** để truyền tín hiệu; GND logic relay phải chung GND ESP32 ống. Khung V2 có câu chung GND bơm, còn HTML mô tả mạch bơm tách biệt: bản tích hợp theo HTML thực tế TV1 đã lắp. Không suy rộng điều này sang mạch dùng MOSFET/transistor hay module có đấu nguồn khác.

Hai bộ chia áp 10k/20k cho điện áp danh định 5×20/(10+20) ≈ 3,33V. Cần kiểm tra mức tín hiệu thực và nguồn; loại ngõ ra cảm biến cụ thể có thể khác nhau. Không đưa ECHO/tín hiệu 5V trực tiếp vào GPIO. LED đỏ sáng xác nhận mức kích module; vẫn cần kiểm tra tiếp điểm COM–NO và bơm thật.

## Diode bơm đã lắp theo xác nhận TV1

Mắc diode **song song hai đầu bơm DC**, sát bơm: đầu có vạch (cathode) tới cực + bơm, đầu không vạch (anode) tới cực − bơm. Diode phân cực ngược lúc bơm đang chạy. Không mắc diode nối tiếp bơm, không nối tắt COM–NO. Diode ở cuộn relay trên module không thay thế diode ở động cơ. Chọn diode theo dòng động cơ và xung lúc ngắt; chưa có số đo dòng nên chưa chốt mã linh kiện. Tắt nguồn khi đấu, kiểm tra cực trước khi cấp lại.

```text
Adapter +5V ── COM  relay  NO ──┬── (+) BƠM (−) ──┬── Adapter −
                              │                 │
                              └── K | diode | A ┘
                                  vạch ở K
```



## Danh sách linh kiện

2 ESP32 esp32dev CH340, HC-SR04, YF-S401, module relay5V, bơmDC5V, nguồn bơm riêng, diode chống xung ngược, điện trở chia áp10k/20k cho hai tín hiệu, breadboard/dây, ống nước, hai bình và vòi xả. CH340 là USB–UART, không quyết định chất lượng nguồn cả board.

## Ảnh prototype

Thêm ảnh thật vào hardware/photos/, ít nhất toàn mạch và cận chân/chia áp/diode. Hiện chưa bổ sung ảnh thật trong bộ sạch; HTML reference/mo-phong-breadboard-2node.html là mô phỏng, không tính ảnh sản phẩm.
