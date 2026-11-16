FROM eclipse-mosquitto:2.0.22
USER root
COPY mosquitto.conf /mosquitto/config/mosquitto.conf
COPY start.sh /start-wms.sh
RUN chmod +x /start-wms.sh
ENTRYPOINT ["/bin/sh", "/start-wms.sh"]
