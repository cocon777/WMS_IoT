# Chứng chỉ local

Sinh CA/certificate riêng bằng tools/setup-local.ps1 và generate_certs.py; giữ ca.key/server.key local. DNS SAN mosquitto phục vụ kiểm peer MQTT, IP SAN cho laptop demo. Không đưa key/certificate runtime vào gói bàn giao. Không tắt kiểm chứng TLS.
