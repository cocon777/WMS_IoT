#pragma once
// Copy to secrets.h (ignored by Git). Each ESP32 has its own MQTT password.
#define WIFI_SSID "YOUR_2G4_WIFI"
#define WIFI_PASSWORD ""
#define MQTT_HOST "192.168.1.10"
#define MQTT_PORT 8883
#define MQTT_USE_TLS true
#define MQTT_TLS_SERVER_NAME "mosquitto" // DNS identity in server certificate; MQTT_HOST stays the LAN IP
// Copy full deployment/certs/ca.crt PEM including BEGIN/END lines here.
#define MQTT_CA_PEM R"PEM(PASTE_CA_CERTIFICATE_HERE)PEM"
#if WMS_TANK
#define DEVICE_ID "wms-tank-01"
#define MQTT_PASSWORD ""
#else
#define DEVICE_ID "wms-pipe-01"
#define MQTT_PASSWORD ""
#endif
