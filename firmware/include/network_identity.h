#pragma once
#include <stdint.h>

namespace wms {
inline bool usableMac(const uint8_t mac[6]) {
  bool zero=true, ff=true;
  for(int i=0;i<6;i++) { zero=zero&&mac[i]==0; ff=ff&&mac[i]==255; }
  return !zero&&!ff&&!(mac[0]&1); // unicast only; locally administered is valid
}
inline void fallbackBaseMac(const char* deviceId,uint8_t mac[6]) {
  uint32_t hash=2166136261UL;
  for(const char* p=deviceId;*p;++p) { hash^=uint8_t(*p); hash*=16777619UL; }
  mac[0]=0x02; mac[1]=0x57; // locally administered, unicast (not an Espressif OUI)
  mac[2]=hash>>24; mac[3]=hash>>16; mac[4]=hash>>8;
  mac[5]=hash&0xfc; // reserve the derived AP/BT/Ethernet offsets
}
}
