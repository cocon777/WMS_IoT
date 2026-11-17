// Standalone flow calibration sketch for the PIPE ESP32 only (Arduino IDE).
// Active HIGH relay confirmed by TV1. Install flyback diode before pumping.
// h: run at most 5 seconds; l: stop; c: clear pulses only when stopped.
// Collect measured water; coefficient = counted pulses / measured litres.
const int FLOW=27, RELAY=26;
volatile uint32_t pulses=0;
portMUX_TYPE pulseMux=portMUX_INITIALIZER_UNLOCKED;
bool pumping=false; uint32_t started=0;
void IRAM_ATTR onPulse() { portENTER_CRITICAL_ISR(&pulseMux); ++pulses; portEXIT_CRITICAL_ISR(&pulseMux); }
void setup() {
  digitalWrite(RELAY,LOW); pinMode(RELAY,OUTPUT); digitalWrite(RELAY,LOW);
  Serial.begin(115200); pinMode(FLOW,INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW),onPulse,FALLING);
  Serial.println("h: pump <=5s | l: stop | c: clear when stopped. Water source must contain water.");
}
void loop() {
  if(pumping && uint32_t(millis()-started)>=5000) { pumping=false; digitalWrite(RELAY,LOW); }
  while(Serial.available()) {
    char c=Serial.read();
    if(c=='l') { pumping=false; digitalWrite(RELAY,LOW); }
    if(c=='c' && !pumping) { portENTER_CRITICAL(&pulseMux); pulses=0; portEXIT_CRITICAL(&pulseMux); }
    if(c=='h' && !pumping) { started=millis(); pumping=true; digitalWrite(RELAY,HIGH); }
  }
  static uint32_t last=0;
  if(uint32_t(millis()-last)>=1000) {
    last=millis(); portENTER_CRITICAL(&pulseMux); uint32_t p=pulses; portEXIT_CRITICAL(&pulseMux);
    Serial.printf("pulses=%lu relay=%d\n",(unsigned long)p,pumping);
  }
  delay(5);
}
