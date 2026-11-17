#pragma once
#include <stdint.h>
#include <math.h>

namespace wms {
// Median across three measurements rejects isolated echoes; EMA reduces jitter.
// Invalid echoes stay invalid: never publish the previous value as a fresh sample.
class DistanceFilter {
  float values_[3]={}, value_=NAN;
  uint8_t count_=0, next_=0;
  uint32_t lastValid_=0;
public:
  float update(float measured,uint32_t now,float fullDistance=NAN) {
    if(!isfinite(measured)) return NAN;
    if(count_ && uint32_t(now-lastValid_)>5000) { count_=next_=0; value_=NAN; }
    lastValid_=now; values_[next_]=measured; next_=(next_+1)%3;
    if(count_<3) ++count_;
    float sorted[3]; for(uint8_t i=0;i<count_;++i) sorted[i]=values_[i];
    for(uint8_t i=0;i<count_;++i) for(uint8_t j=i+1;j<count_;++j)
      if(sorted[j]<sorted[i]) { float swap=sorted[i]; sorted[i]=sorted[j]; sorted[j]=swap; }
    const float median=sorted[count_/2];
    if(!isfinite(value_) || (isfinite(fullDistance)&&median<=fullDistance)) value_=median;
    else if(fabsf(median-value_)<=0.08f) value_=median;
    else value_+=0.5f*(median-value_);
    return value_;
  }
};
inline float levelPercent(float distance, float empty, float full) {
  if (!isfinite(distance) || empty <= full) return NAN;
  float pct = 100.0f * (empty - distance) / (empty - full);
  return pct < 0 ? 0 : (pct > 100 ? 100 : pct);
}
inline float tankLevelPercent(float distance, float sensorToBottom, float waterHeight) {
  // tank_height_cm must also be the percent-to-cm span used by backend leak rules.
  if (!isfinite(sensorToBottom) || !isfinite(waterHeight) || waterHeight <= 0 ||
      sensorToBottom - waterHeight < 2.0f) return NAN;
  return levelPercent(distance, sensorToBottom, sensorToBottom - waterHeight);
}
inline bool expired(int64_t now, int64_t issued) {
  return now < 1700000000 || issued < 1700000000 || now - issued > 10 || issued - now > 2;
}
inline bool elapsed(uint32_t now, uint32_t start, uint32_t duration) {
  return uint32_t(now - start) >= duration; // handles millis() wrap
}
inline float flowLpm(uint32_t pulses, float pulsesPerLitre, uint32_t intervalMs) {
  return pulsesPerLitre > 0 && intervalMs > 0 ? pulses * 60000.0f / (pulsesPerLitre * intervalMs) : NAN;
}
}
