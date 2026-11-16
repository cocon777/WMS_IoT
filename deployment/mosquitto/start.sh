#!/bin/sh
set -eu
if [ ! -s /mosquitto/data/dynamic-security.json ]; then
  mosquitto_ctrl dynsec init /mosquitto/data/dynamic-security.json "$MQTT_ADMIN_USERNAME" "$MQTT_ADMIN_PASSWORD"
fi
mkdir -p /mosquitto/data/tls
cp /certs/server.crt /mosquitto/data/tls/server.crt
cp /certs/server.key /mosquitto/data/tls/server.key
chmod 600 /mosquitto/data/tls/server.key
chown -R mosquitto:mosquitto /mosquitto/data
exec mosquitto -c /mosquitto/config/mosquitto.conf
