#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_netif.h>
#include <esp_mac.h>
#include <esp_system.h>
#include <WiFiClientSecure.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <sys/time.h>
#include <time.h>
#include <algorithm>
#include "hardware_config.h"
#include "control_logic.h"
#include "network_identity.h"
#include "broker_tls_client.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif
#ifndef MQTT_TLS_SERVER_NAME
#define MQTT_TLS_SERVER_NAME MQTT_HOST
#endif

constexpr const char* FIRMWARE_VERSION = WMS_TANK ? "tv1-0.3.4" : "tv1-0.3.2";

struct Config { uint32_t version=0, sample=1, maxRun=60; float height=WATER_HEIGHT_CM, low=20, high=100; };
Config config;
portMUX_TYPE guard = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t pulses=0;
bool pumping=false, dryFault=false, networkOnline=false;
uint32_t pumpStart=0, pumpDuration=0, lastFlow=0, networkTick=0;
QueueHandle_t samples, incoming;
Preferences prefs;
char bootId[17];
struct Sample { uint64_t seq; int64_t tsMs; float distance, level, flow, total; bool pump; int rssi; };
struct Incoming { char kind; char payload[1200]; };
struct CachedAck { String id, result, reason; };
CachedAck recent[16]; uint8_t recentNext=0;

Config readConfig() { portENTER_CRITICAL(&guard); Config c=config; portEXIT_CRITICAL(&guard); return c; }
bool pumpState() { portENTER_CRITICAL(&guard); bool p=pumping; portEXIT_CRITICAL(&guard); return p; }
void IRAM_ATTR onPulse() { portENTER_CRITICAL_ISR(&guard); ++pulses; portEXIT_CRITICAL_ISR(&guard); }
uint32_t pulseCount() { portENTER_CRITICAL(&guard); uint32_t p=pulses; portEXIT_CRITICAL(&guard); return p; }
int64_t nowMs() { timeval tv; gettimeofday(&tv,nullptr); return int64_t(tv.tv_sec)*1000+tv.tv_usec/1000; }
String iso(int64_t ms) {
  time_t sec=ms/1000; tm utc; gmtime_r(&sec,&utc); char b[32], base[24];
  strftime(base,sizeof(base),"%Y-%m-%dT%H:%M:%S",&utc);
  snprintf(b,sizeof(b),"%s.%03dZ",base,int(ms%1000)); return String(b);
}
void stopPump(const char* why) {
  portENTER_CRITICAL(&guard);
  bool was=pumping; pumping=false; digitalWrite(RELAY_PIN,RELAY_OFF);
  portEXIT_CRITICAL(&guard);
  if(was) Serial.printf("PUMP OFF: %s\n",why);
}
// Separate task: network operations can block without extending the pump run deadline.
void safetyTask(void*) {
  uint32_t prev=0;
  for(;;) {
    uint32_t now=millis(); const char* reason=nullptr;
    portENTER_CRITICAL(&guard);
    if(pulses!=prev) { prev=pulses; lastFlow=now; }
    if(pumping) {
      if(!networkOnline || wms::elapsed(now,networkTick,NETWORK_STALE_MS)) reason="network unavailable";
      else if(wms::elapsed(now,pumpStart,pumpDuration)) reason="duration limit";
      else if(wms::elapsed(now,lastFlow,NO_FLOW_TIMEOUT_MS)) { dryFault=true; reason="no flow"; }
      if(reason) { pumping=false; digitalWrite(RELAY_PIN,RELAY_OFF); }
    }
    portEXIT_CRITICAL(&guard);
    if(reason) Serial.printf("PUMP OFF: %s\n",reason);
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}
float distanceCm() {
  float values[5]; int count=0;
  for(int i=0;i<5;++i) {
    digitalWrite(TRIG_PIN,LOW); delayMicroseconds(2); digitalWrite(TRIG_PIN,HIGH);
    delayMicroseconds(10); digitalWrite(TRIG_PIN,LOW);
    auto us=pulseIn(ECHO_PIN,HIGH,25000);
    float cm=us*0.0343f/2;
    if(us && cm>=2 && cm<=400) values[count++]=cm;
    delay(60);
  }
  if(count<3) return NAN;
  std::sort(values,values+count); return values[count/2];
}
bool persistAcks() {
  DynamicJsonDocument d(4096); JsonArray a=d.to<JsonArray>();
  for(auto &r:recent) if(r.id.length()) { auto o=a.createNestedObject(); o["id"]=r.id; o["result"]=r.result; o["reason"]=r.reason; }
  String data; serializeJson(d,data); return prefs.putString("acks",data)==data.length();
}
void sendAck(MQTTClient& mqtt,const String& id,const String& result,const String& reason) {
  StaticJsonDocument<384> d; d["cmd_id"]=id; d["result"]=result;
  if(reason.length()) d["reason"]=reason; else d["reason"]=nullptr;
  d["ts"]=iso(nowMs()); String payload; serializeJson(d,payload);
  mqtt.publish(String("wms/")+DEVICE_ID+"/ack",payload,false,1);
}
void command(MQTTClient& mqtt,JsonDocument& d) {
  String id=d["cmd_id"]|""; if(id.length()==0 || id.length()>64) return;
  for(auto &r:recent) if(r.id==id) { sendAck(mqtt,id,r.result,r.reason); return; }
  String reason="", value=d["value"]|""; Config c=readConfig();
  String issued=d["issued_at"]|""; tm parsed={};
  char* end=strptime(issued.c_str(),"%Y-%m-%dT%H:%M:%SZ",&parsed);
  int64_t issuedAt=end && *end=='\0' ? mktime(&parsed) : 0; // process TZ is UTC0
  uint32_t duration=d["duration_s"]|0;
  if(WMS_TANK) reason="wrong_node";
  else if(String(d["action"]|"")!="pump" || (value!="on" && value!="off")) reason="invalid_command";
  else if(wms::expired(time(nullptr),issuedAt)) reason="expired";
  else if(value=="on") {
    if(!PUMP_ENABLED || PULSES_PER_LITRE<=0) reason="calibration_required";
    else if(!d["duration_s"].is<unsigned int>() || duration<1 || duration>c.maxRun || duration>HARD_MAX_RUN_MS/1000) reason="over_limit";
    else { portENTER_CRITICAL(&guard);
      if(dryFault) reason="no_flow_latched_send_off";
      else if(pumping) reason="busy";
      portEXIT_CRITICAL(&guard); }
  }
  // Persist the identity BEFORE energising relay: a reset must never replay an ON command.
  uint8_t slot=recentNext;
  recent[slot]={id,reason.length()?"fail":"ok",reason}; recentNext=(recentNext+1)%16;
  if(!persistAcks()) { reason="nvs_failure"; recent[slot]={id,"fail",reason}; }
  if(reason.length()==0) {
    if(value=="off") { stopPump("remote off"); portENTER_CRITICAL(&guard); dryFault=false; portEXIT_CRITICAL(&guard); }
    else {
      portENTER_CRITICAL(&guard);
      pumpStart=lastFlow=millis(); pumpDuration=duration*1000;
      pumping=true; digitalWrite(RELAY_PIN,RELAY_ON);
      portEXIT_CRITICAL(&guard);
    }
  }
  sendAck(mqtt,id,reason.length()?"fail":"ok",reason);
}
void applyConfig(JsonDocument& d) {
  Config c=readConfig();
  if(!d["version"].is<unsigned int>() || d["version"].as<uint32_t>()<=c.version) return;
  if(!d["sample_interval_s"].is<unsigned int>() || !d["pump_max_run_s"].is<unsigned int>() ||
     !d["tank_height_cm"].is<float>() || !d["low_pct"].is<float>() || !d["high_pct"].is<float>()) return;
  c.version=d["version"]; c.sample=d["sample_interval_s"]; c.maxRun=d["pump_max_run_s"];
  c.height=d["tank_height_cm"]; c.low=d["low_pct"]; c.high=d["high_pct"];
  if(c.sample<1 || c.sample>300 || c.maxRun<5 || c.maxRun>120 || !isfinite(c.height) || c.height<5 || c.height>500 ||
     !isfinite(c.low) || !isfinite(c.high) || c.low<0 || c.high>100 || c.high-c.low<10) return;
  String wire; serializeJson(d,wire);
  if(prefs.putString("config",wire)!=wire.length()) { Serial.println("NVS config write failed"); return; }
  portENTER_CRITICAL(&guard); config=c;
  if(pumping && pumpDuration>c.maxRun*1000) pumpDuration=c.maxRun*1000;
  portEXIT_CRITICAL(&guard);
  Serial.printf("CONFIG applied v%lu\n",(unsigned long)c.version);
}
void status(MQTTClient& mqtt) {
  StaticJsonDocument<384> d; d["status"]="online"; d["fw_version"]=FIRMWARE_VERSION;
  d["free_heap"]=ESP.getFreeHeap(); d["config_version"]=readConfig().version;
  String payload; serializeJson(d,payload);
  mqtt.publish(String("wms/")+DEVICE_ID+"/status",payload,true,1);
}
String telemetry(const Sample& s) {
  StaticJsonDocument<768> d; d["device_id"]=DEVICE_ID; d["boot_id"]=bootId; d["seq"]=s.seq;
  d["ts"]=iso(s.tsMs); d["rssi"]=s.rssi;
  if(WMS_TANK) { d["distance_cm"]=s.distance; d["level_pct"]=s.level; d["unit"]["distance"]="cm"; d["unit"]["level"]="%"; }
  else { d["flow_lpm"]=s.flow; d["flow_total_l"]=s.total; d["pump_on"]=s.pump; d["unit"]["flow"]="L/min"; d["unit"]["total"]="L"; }
  String out; serializeJson(d,out); return out;
}
void networkTask(void*) {
  WiFiClient plain; BrokerTlsClient secure(MQTT_TLS_SERVER_NAME); MQTTClient mqtt(2048);
  if(MQTT_USE_TLS) { secure.setCACert(MQTT_CA_PEM); secure.setHandshakeTimeout(3); mqtt.begin(MQTT_HOST,MQTT_PORT,secure); }
  else mqtt.begin(MQTT_HOST,MQTT_PORT,plain);
  plain.setTimeout(3000); secure.setTimeout(3); mqtt.setOptions(30,true,3000);
  mqtt.setWill((String("wms/")+DEVICE_ID+"/status").c_str(),"{\"status\":\"offline\"}",true,1);
  mqtt.onMessage(+[](String& topic,String& payload) {
    if(payload.length()>=sizeof(Incoming::payload)) return;
    Incoming in={}; in.kind=topic.endsWith("/cmd")?'c':'f'; payload.toCharArray(in.payload,sizeof(in.payload));
    if(xQueueSend(incoming,&in,0)!=pdTRUE) Serial.println("RX queue full");
  });
  uint32_t nextAttempt=0, backoff=1000, heartbeat=0, flush=0, lastReport=0, lastWifiRecovery=millis();
  static Sample ring[TELEMETRY_BUFFER_SAMPLES]; size_t head=0,count=0;
  Sample newest={}; bool newestPending=false;
  for(;;) {
    uint32_t now=millis(); Sample s;
    while(xQueueReceive(samples,&s,0)==pdTRUE) {
      if(newestPending) {
        if(count==TELEMETRY_BUFFER_SAMPLES) { head=(head+1)%TELEMETRY_BUFFER_SAMPLES; --count; Serial.println("BUFFER drop oldest"); }
        ring[(head+count)%TELEMETRY_BUFFER_SAMPLES]=newest; ++count;
      }
      newest=s; newestPending=true;
    }
    bool wifi=WiFi.status()==WL_CONNECTED;
    if(wms::elapsed(now,lastReport,5000)) {
      lastReport=now;
      wifi_ap_record_t ap={}; bool associated=esp_wifi_sta_get_ap_info(&ap)==ESP_OK;
      esp_netif_dhcp_status_t dhcp=ESP_NETIF_DHCP_INIT;
      auto netif=esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
      bool dhcpKnown=netif && esp_netif_dhcpc_get_status(netif,&dhcp)==ESP_OK;
      Serial.printf("NET wifi_status=%d ip=%s rssi=%d time_ready=%d mqtt=%d associated=%d dhcp=%s\n",
        int(WiFi.status()),WiFi.localIP().toString().c_str(),wifi?WiFi.RSSI():-120,
        time(nullptr)>1700000000,mqtt.connected(),associated,
        !dhcpKnown?"unknown":dhcp==ESP_NETIF_DHCP_STARTED?"started":dhcp==ESP_NETIF_DHCP_STOPPED?"stopped":"init");
    }
    if(wifi) lastWifiRecovery=now;
    else if(wms::elapsed(now,lastWifiRecovery,45000)) {
      lastWifiRecovery=now;
      wifi_ap_record_t ap={};
      if(esp_wifi_sta_get_ap_info(&ap)==ESP_OK) {
        // Associated but no lease: renew DHCP, never guess an address on the user's LAN.
        bool ok=WiFi.config(IPAddress(0,0,0,0),IPAddress(0,0,0,0),IPAddress(0,0,0,0));
        Serial.printf("WIFI DHCP restart requested ok=%d\n",ok);
      } else {
        WiFi.disconnect(false,false); // keep credentials; no NVS erase
        Serial.printf("WIFI retry begin status=%d\n",int(WiFi.begin(WIFI_SSID,WIFI_PASSWORD)));
      }
    }
    if(!wifi && mqtt.connected()) mqtt.disconnect();
    if(wifi && time(nullptr)>1700000000 && !mqtt.connected() && int32_t(now-nextAttempt)>=0) {
      if(mqtt.connect(DEVICE_ID,DEVICE_ID,MQTT_PASSWORD)) {
        bool ok=mqtt.subscribe(String("wms/")+DEVICE_ID+"/config",1);
        if(!WMS_TANK) ok=mqtt.subscribe(String("wms/")+DEVICE_ID+"/cmd",1)&&ok;
        if(ok) { status(mqtt); heartbeat=millis(); backoff=1000; Serial.println("MQTT connected"); }
        else { Serial.println("MQTT subscribe failed"); mqtt.disconnect(); }
      } else {
        Serial.printf("MQTT connect failed: error=%d return_code=%d\n",int(mqtt.lastError()),int(mqtt.returnCode()));
        if(MQTT_USE_TLS) { char error[160]={}; int code=secure.lastError(error,sizeof(error)); Serial.printf("TLS error=%d %s\n",code,error); }
      }
      nextAttempt=millis()+backoff+(esp_random()%250); backoff=std::min(backoff*2,uint32_t(30000));
    }
    if(mqtt.connected() && !mqtt.loop()) Serial.printf("MQTT loop failed error=%d\n",int(mqtt.lastError()));
    portENTER_CRITICAL(&guard); networkOnline=wifi&&mqtt.connected(); networkTick=millis(); portEXIT_CRITICAL(&guard);
    Incoming in;
    if(xQueueReceive(incoming,&in,0)==pdTRUE) {
      DynamicJsonDocument d(2048);
      if(!deserializeJson(d,in.payload)) { if(in.kind=='c') command(mqtt,d); else { applyConfig(d); if(mqtt.connected()) status(mqtt); } }
    }
    if(mqtt.connected() && wms::elapsed(millis(),heartbeat,30000)) { status(mqtt); heartbeat=millis(); }
    // Prioritize the newest sample after reconnect. History must not hold up
    // live level/pump guards. Unsent older samples remain in the bounded ring.
    // Total remains capped at two publishes/sec, without sending samples twice.
    if(mqtt.connected() && (newestPending||count) && wms::elapsed(millis(),flush,500)) {
      bool live=newestPending; Sample &front=live?newest:ring[head];
      bool done=nowMs()-front.tsMs>240000;
      if(done) Serial.println("BUFFER expired >240s");
      else {
        uint32_t started=millis();
        done=mqtt.publish(String("wms/")+DEVICE_ID+"/telemetry",telemetry(front),false,TELEMETRY_QOS);
        if(!done) Serial.printf("MQTT telemetry failed error=%d elapsed_ms=%lu backlog=%u live=%d\n",
          int(mqtt.lastError()),(unsigned long)(millis()-started),unsigned(count),live);
      }
      if(done) { if(live) newestPending=false; else { head=(head+1)%TELEMETRY_BUFFER_SAMPLES; --count; } }
      flush=millis();
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}
void setup() {
  if(!WMS_TANK) { digitalWrite(RELAY_PIN,RELAY_OFF); pinMode(RELAY_PIN,OUTPUT); digitalWrite(RELAY_PIN,RELAY_OFF); }
  Serial.begin(115200); delay(100);
  esp_reset_reason_t reset=esp_reset_reason();
  const char* resetName="OTHER";
  switch(reset) {
    case ESP_RST_POWERON:resetName="POWERON";break;
    case ESP_RST_SW:resetName="SOFTWARE";break;
    case ESP_RST_PANIC:resetName="PANIC";break;
    case ESP_RST_INT_WDT:resetName="INT_WATCHDOG";break;
    case ESP_RST_TASK_WDT:resetName="TASK_WATCHDOG";break;
    case ESP_RST_WDT:resetName="WATCHDOG";break;
    case ESP_RST_BROWNOUT:resetName="BROWNOUT";break;
    case ESP_RST_EXT:resetName="EXTERNAL_RESET";break;
    default:break;
  }
  Serial.printf("RESET reason=%d name=%s\n",int(reset),resetName);
  // Some supplied boards report an invalid factory MAC. Set a RAM override before
  // any network interface is initialized; never burn eFuse or replace a valid MAC.
  uint8_t factoryMac[6]={};
  esp_err_t macRead=esp_efuse_mac_get_default(factoryMac);
  bool useFallbackMac=macRead!=ESP_OK || !wms::usableMac(factoryMac);
  uint8_t requestedMac[6]={};
  if(useFallbackMac) {
    wms::fallbackBaseMac(DEVICE_ID,requestedMac);
    esp_err_t result=esp_base_mac_addr_set(requestedMac);
    Serial.printf("WIFI factory MAC invalid read=%d; local MAC=%02X:%02X:%02X:%02X:%02X:%02X override=%d (RAM only)\n",
      int(macRead),requestedMac[0],requestedMac[1],requestedMac[2],requestedMac[3],requestedMac[4],requestedMac[5],int(result));
    if(result!=ESP_OK) { Serial.println("FATAL network identity setup failed"); while(true) delay(1000); }
  }
  setenv("TZ","UTC0",1); tzset();
  snprintf(bootId,sizeof(bootId),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  prefs.begin(WMS_TANK?"wms-tank":"wms-pipe",false);
  DynamicJsonDocument saved(4096); String old=prefs.isKey("config")?prefs.getString("config",""):String();
  if(old.length() && !deserializeJson(saved,old)) applyConfig(saved);
  saved.clear();
  String savedAcks=prefs.isKey("acks")?prefs.getString("acks","[]"):String("[]");
  if(!deserializeJson(saved,savedAcks)) {
    for(JsonObject r:saved.as<JsonArray>()) { if(recentNext==16) break; recent[recentNext++]={String(r["id"]|""),String(r["result"]|"fail"),String(r["reason"]|"")}; }
    recentNext%=16;
  }
  if(WMS_TANK) { pinMode(TRIG_PIN,OUTPUT); pinMode(ECHO_PIN,INPUT); }
  else { pinMode(FLOW_PIN,INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(FLOW_PIN),onPulse,FALLING); }
  samples=xQueueCreate(8,sizeof(Sample)); incoming=xQueueCreate(8,sizeof(Incoming));
  if(!samples || !incoming) { Serial.println("FATAL queue allocation"); while(true) delay(1000); }
  WiFi.persistent(false); // network credentials come from secrets.h, not driver NVS
  if(!WiFi.mode(WIFI_STA)) { Serial.println("FATAL WiFi initialization failed"); while(true) delay(1000); }
  if(useFallbackMac) {
    // Some boards/driver blobs ignore a base override. Stop the interface, set
    // its STA address explicitly, then read it back before allowing association.
    esp_err_t stopped=esp_wifi_stop();
    esp_err_t applied=stopped==ESP_OK?esp_wifi_set_mac(WIFI_IF_STA,requestedMac):stopped;
    esp_err_t started=applied==ESP_OK?esp_wifi_start():applied;
    uint8_t actual[6]={}; esp_err_t readback=esp_wifi_get_mac(WIFI_IF_STA,actual);
    bool verified=stopped==ESP_OK&&applied==ESP_OK&&started==ESP_OK&&readback==ESP_OK;
    for(int i=0;i<6;i++) verified=verified&&actual[i]==requestedMac[i];
    Serial.printf("WIFI STA MAC verify=%d stop=%d set=%d start=%d read=%d actual=%02X:%02X:%02X:%02X:%02X:%02X\n",
      verified,int(stopped),int(applied),int(started),int(readback),actual[0],actual[1],actual[2],actual[3],actual[4],actual[5]);
    if(!verified) { Serial.println("FATAL invalid WiFi interface MAC; connection not attempted"); while(true) delay(1000); }
  }
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED)
      Serial.printf("WIFI disconnected reason=%u\n",unsigned(info.wifi_sta_disconnected.reason));
    else if(event==ARDUINO_EVENT_WIFI_STA_CONNECTED)
      Serial.println("WIFI associated; waiting for DHCP IP");
    else if(event==ARDUINO_EVENT_WIFI_STA_GOT_IP)
      Serial.printf("WIFI connected ip=%s channel=%d\n",WiFi.localIP().toString().c_str(),WiFi.channel());
  });
  // One bounded scan at boot before starting the watchdog/tasks. No passwords logged.
  Serial.println("WIFI scanning 2.4GHz for configured SSID...");
  int visible=WiFi.scanNetworks(false,false); bool found=false;
  for(int i=0;i<visible;i++) if(WiFi.SSID(i)==WIFI_SSID) {
    found=true;
    Serial.printf("WIFI target found channel=%d rssi=%d auth=%d\n",WiFi.channel(i),WiFi.RSSI(i),int(WiFi.encryptionType(i)));
  }
  Serial.printf("WIFI scan result=%d target_found=%d\n",visible,found);
  WiFi.scanDelete();
  bool dhcpReady=WiFi.config(IPAddress(0,0,0,0),IPAddress(0,0,0,0),IPAddress(0,0,0,0));
  Serial.printf("WIFI DHCP init ok=%d STA MAC=%s\n",dhcpReady,WiFi.macAddress().c_str());
  Serial.printf("WIFI begin status=%d\n",int(WiFi.begin(WIFI_SSID,WIFI_PASSWORD)));
  configTime(0,0,"pool.ntp.org","time.google.com");
  esp_task_wdt_init(8,true); esp_task_wdt_add(nullptr);
  if(!WMS_TANK && xTaskCreate(safetyTask,"pump-safety",3072,nullptr,3,nullptr)!=pdPASS) { Serial.println("FATAL safety task"); while(true) delay(1000); }
  if(xTaskCreate(networkTask,"mqtt",14336,nullptr,1,nullptr)!=pdPASS) { Serial.println("FATAL network task"); while(true) delay(1000); }
  Serial.printf("BOOT %s role=%s boot=%s pump_enabled=%d\n",DEVICE_ID,WMS_TANK?"tank":"pipe",bootId,PUMP_ENABLED);
}
void loop() {
  static uint32_t lastMeasure=0, lastSample=0, prevPulses=0; static uint64_t seq=0;
  static float flow=0,total=0;
  static wms::DistanceFilter distanceFilter;
  esp_task_wdt_reset(); Config c=readConfig(); uint32_t now=millis();
  if(!WMS_TANK && wms::elapsed(now,lastMeasure,1000)) {
    uint32_t p=pulseCount(), delta=p-prevPulses;
    flow=wms::flowLpm(delta,PULSES_PER_LITRE,now-lastMeasure);
    if(PULSES_PER_LITRE>0) total+=delta/PULSES_PER_LITRE;
    prevPulses=p; lastMeasure=now;
    Serial.printf("FLOW pulses=%lu flow=%.3f total=%.3f calibrated=%d\n",(unsigned long)p,flow,total,PULSES_PER_LITRE>0);
  }
  if(wms::elapsed(now,lastSample,c.sample*1000)) {
    lastSample=now; Sample s={}; s.seq=++seq; s.tsMs=nowMs(); s.rssi=WiFi.status()==WL_CONNECTED?WiFi.RSSI():-120;
    bool valid=s.tsMs>1700000000000LL;
    if(WMS_TANK) { float raw=distanceCm(); s.distance=distanceFilter.update(raw,millis(),SENSOR_TO_BOTTOM_CM-c.height); s.level=wms::tankLevelPercent(s.distance,SENSOR_TO_BOTTOM_CM,c.height); valid=valid&&isfinite(s.distance)&&isfinite(s.level); Serial.printf("TANK raw_cm=%.2f cm=%.2f pct=%.2f geometry_ready=%d\n",raw,s.distance,s.level,isfinite(wms::tankLevelPercent(0,SENSOR_TO_BOTTOM_CM,c.height))); }
    else { s.flow=flow; s.total=total; s.pump=pumpState(); valid=valid&&isfinite(flow); }
    if(valid) { if(xQueueSend(samples,&s,0)!=pdTRUE) Serial.println("SAMPLE queue full"); }
    else Serial.println("SAMPLE skipped: time/sensor/calibration not ready");
  }
  delay(10);
}
