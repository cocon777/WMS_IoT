#pragma once
// Confirmed by TV1 on 2026-11-12. No buzzer in the assembled prototype.
constexpr int TRIG_PIN = 5, ECHO_PIN = 18, FLOW_PIN = 27, RELAY_PIN = 26;
constexpr int RELAY_ON = HIGH;
constexpr int RELAY_OFF = LOW;
// Empty-tank echo reference, NOT the water column height.
// Zero means not measured: tank logs distance but does not publish a guessed level.
constexpr float SENSOR_TO_BOTTOM_CM = 16.5f; // TV1 revised empty reference 2026-11-15; was 17cm
constexpr float WATER_HEIGHT_CM = 8.0f; // TV1 2026-11-15: full8cm; sensor-to-full gap8.5cm
// TV1 reported 3404/440mL, 4742/580mL, 5150/610mL on 2026-11-13.
// Held-out check: 6378 pulses / 800mL -> 781.90mL with this coefficient (-2.26%).
constexpr float PULSES_PER_LITRE = 8157.0552f;
constexpr bool PUMP_ENABLED = true; // TV1 confirmed flyback diode installed; ON still needs a valid command
constexpr uint32_t HARD_MAX_RUN_MS = 60000; // refill watchdog; backend stops earlier at full level
constexpr uint32_t NO_FLOW_TIMEOUT_MS = 10000;
constexpr uint32_t NETWORK_STALE_MS = 4000;
constexpr size_t TELEMETRY_BUFFER_SAMPLES = 180; // ~3 minutes at demo sample_interval_s=1
constexpr int TELEMETRY_QOS = 1; // may set 0 for the QoS comparison experiment
