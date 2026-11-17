const int TRIG = 5, ECHO = 18, FLOW = 27, RELAY = 26;
volatile uint32_t pulses = 0;
void IRAM_ATTR onPulse() { pulses++; }

float cm() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long d = pulseIn(ECHO, HIGH, 30000);
  return d == 0 ? -1 : d * 0.0343 / 2;
}

void setup() {
  // Giữ relay TẮT khi chương trình bắt đầu chạy
  digitalWrite(RELAY, LOW);
  pinMode(RELAY, OUTPUT);
  digitalWrite(RELAY, LOW);

  Serial.begin(115200);

  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);

  pinMode(FLOW, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW), onPulse, FALLING);

  Serial.println("Phim h: relay BAT | l: relay TAT | c: xoa dem xung");
}

void loop() {
  static uint32_t t = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'h') digitalWrite(RELAY, HIGH);
    if (c == 'l') digitalWrite(RELAY, LOW);
    if (c == 'c') pulses = 0;
  }
  // Mức chân relay làm relay đóng (có tiếng tách) chính là giá trị RELAY_ON cần ghi vào firmware chính
  if (millis() - t >= 1000) {
    t = millis();
    noInterrupts();
    uint32_t p = pulses;
    interrupts();
    Serial.printf("khoang cach = %.1f cm | xung = %lu | relay chan = %d\n", cm(), (unsigned long)p, digitalRead(RELAY));
  }
}
