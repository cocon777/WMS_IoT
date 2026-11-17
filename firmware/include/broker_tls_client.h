#pragma once
#include <WiFiClientSecure.h>

// Keep the TCP route (LAN IP) separate from the certificate's DNS identity.
// Arduino ESP32 2.x uses mbedTLS with DNS-name matching; IP SANs alone are not
// enough for that matcher. CA, name and validity checks remain enabled.
class BrokerTlsClient : public WiFiClientSecure {
  const char* peerName_;
public:
  explicit BrokerTlsClient(const char* peerName):peerName_(peerName) {}
  using WiFiClientSecure::connect;
  int connect(const char* host,uint16_t port) override {
    IPAddress address;
    if(!WiFi.hostByName(host,address)) return 0;
    return connect(address,port);
  }
  int connect(IPAddress address,uint16_t port) override {
    if(!peerName_ || !*peerName_ || !_CA_cert || !*_CA_cert || _use_insecure) return 0;
    return WiFiClientSecure::connect(address,port,peerName_,_CA_cert,_cert,_private_key);
  }
};
