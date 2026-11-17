"""Interactive local-only secrets.h generation. No upload or physical actuation."""
from getpass import getpass
import ipaddress
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root/'firmware/include/secrets.h'
if target.exists():
    raise SystemExit('secrets.h exists; kept unchanged. Edit locally or archive it before regeneration.')
ca = (root/'deployment/certs/ca.crt').read_text(encoding='ascii')
ssid = input('Wi-Fi 2.4GHz SSID: ').strip()
wifi = getpass('Wi-Fi password: ')
host = input('Computer LAN IPv4 (certificate SAN): ').strip()
ipaddress.IPv4Address(host)
port = int(input('MQTT TLS port [8883]: ') or '8883')
if not 1 <= port <= 65535 or not ssid:
    raise SystemExit('Invalid port or empty SSID')
from cryptography import x509
cert = x509.load_pem_x509_certificate((root/'deployment/certs/server.crt').read_bytes())
if 'mosquitto' not in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName):
    raise SystemExit('Server certificate must include DNS SAN mosquitto for the ESP32 TLS peer identity.')
if ipaddress.IPv4Address(host) not in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress):
    raise SystemExit('LAN IP not in server certificate SAN; regenerate certificates with correct IP first.')
tank = getpass('MQTT password from provisioning wms-tank-01: ')
pipe = getpass('MQTT password from provisioning wms-pipe-01: ')
if not tank or not pipe:
    raise SystemExit('Both node passwords are required.')
q = lambda s: json.dumps(s, ensure_ascii=True)
target.write_text(f'''#pragma once
#define WIFI_SSID {q(ssid)}
#define WIFI_PASSWORD {q(wifi)}
#define MQTT_HOST {q(host)}
#define MQTT_PORT {port}
#define MQTT_USE_TLS true
#define MQTT_TLS_SERVER_NAME "mosquitto"
#define MQTT_CA_PEM {q(ca)}
#if WMS_TANK
#define DEVICE_ID "wms-tank-01"
#define MQTT_PASSWORD {q(tank)}
#else
#define DEVICE_ID "wms-pipe-01"
#define MQTT_PASSWORD {q(pipe)}
#endif
''', encoding='utf-8')
print('Created ignored firmware/include/secrets.h. Build/upload each correct environment yourself; no flash performed.')
