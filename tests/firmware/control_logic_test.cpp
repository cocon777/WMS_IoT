#include <cassert>
#include "../../firmware/include/control_logic.h"
#include "../../firmware/include/network_identity.h"
#include <cstring>
int main() {
  uint8_t zero[6]={},ff[6]={255,255,255,255,255,255},multicast[6]={1,2,3,4,5,6};
  assert(!wms::usableMac(zero)); assert(!wms::usableMac(ff)); assert(!wms::usableMac(multicast));
  uint8_t tank[6],tankAgain[6],pipe[6];
  wms::fallbackBaseMac("wms-tank-01",tank); wms::fallbackBaseMac("wms-tank-01",tankAgain); wms::fallbackBaseMac("wms-pipe-01",pipe);
  assert(wms::usableMac(tank)&&wms::usableMac(pipe));
  assert((tank[0]&3)==2 && (pipe[0]&3)==2);
  assert(std::memcmp(tank,tankAgain,6)==0); assert(std::memcmp(tank,pipe,6)!=0);
  assert((tank[5]&3)==0 && (pipe[5]&3)==0);
  // Current profile: D016.5/H8; low37.5%=3cm at13.5cm; full at8.5cm.
  assert(wms::tankLevelPercent(16.5f,16.5f,8)==0);
  assert(wms::tankLevelPercent(12.5f,16.5f,8)==50);
  assert(wms::tankLevelPercent(8.5f,16.5f,8)==100);
  assert(fabs(wms::tankLevelPercent(13.5f,16.5f,8)-37.5f)<0.001);
  wms::DistanceFilter filtered;
  assert(filtered.update(12,1000,8.5f)==12);
  assert(filtered.update(12,2000,8.5f)==12);
  assert(filtered.update(14,3000,8.5f)==12); // isolated two-cm echo rejected
  assert(filtered.update(12,4000,8.5f)==12);
  assert(isnan(filtered.update(NAN,4500,8.5f))); // no stale value masquerading as new
  filtered.update(8.5f,5000,8.5f);
  assert(filtered.update(8.5f,6000,8.5f)==8.5f); // confirmed full bypasses EMA lag
  assert(filtered.update(13,12000,8.5f)==13); // long gap resets the filter
  // TV1 2026-11-15: empty16.5cm, full6.5cm, H10cm; LOW3cm at distance13.5cm.
  assert(wms::tankLevelPercent(16.5f,16.5f,10)==0);
  assert(wms::tankLevelPercent(11.5f,16.5f,10)==50);
  assert(wms::tankLevelPercent(6.5f,16.5f,10)==100);
  assert(fabs(wms::tankLevelPercent(13.5f,16.5f,10)-30)<0.001);
  assert(wms::tankLevelPercent(17,16.5f,10)==0);
  assert(wms::tankLevelPercent(6,16.5f,10)==100);
  assert(fabs(wms::tankLevelPercent(16.46f,16.5f,10)-0.4f)<0.001);
  // Previous tabletop geometry: 17cm sensor height, 12cm full water column.
  assert(wms::tankLevelPercent(17,17,12)==0);
  assert(wms::tankLevelPercent(11,17,12)==50);
  assert(wms::tankLevelPercent(5,17,12)==100);
  assert(fabs(wms::tankLevelPercent(13,17,12)-33.333333)<0.001);
  assert(fabs(wms::tankLevelPercent(12.2f,17,12)-40)<0.001);
  assert(fabs(wms::tankLevelPercent(7.4f,17,12)-80)<0.001);
  assert(wms::levelPercent(15,15,5)==0);
  assert(wms::levelPercent(10,15,5)==50);
  assert(wms::levelPercent(5,15,5)==100);
  assert(wms::levelPercent(2,15,5)==100);
  assert(isnan(wms::levelPercent(5,5,5)));
  // Mounting gap must not inflate the backend's cm/min scale. Bottom remains 0%.
  assert(wms::tankLevelPercent(20,20,15)==0);
  assert(wms::tankLevelPercent(12.5,20,15)==50);
  assert(wms::tankLevelPercent(5,20,15)==100);
  assert(fabs(wms::tankLevelPercent(16,20,15)-26.666667)<0.001);
  assert(isnan(wms::tankLevelPercent(10,0,14.5)));
  assert(isnan(wms::tankLevelPercent(10,15,14.5)));
  assert(isnan(wms::tankLevelPercent(NAN,20,15)));
  assert(wms::expired(1800000011,1800000000));
  assert(!wms::expired(1800000010,1800000000));
  assert(wms::expired(1800000000,1800000003));
  assert(wms::elapsed(20,0xfffffff0U,36));
  assert(!wms::elapsed(19,0xfffffff0U,36));
  assert(fabs(wms::flowLpm(100,1000,1000)-6.0)<0.001);
  assert(isnan(wms::flowLpm(1,0,1000)));
}
