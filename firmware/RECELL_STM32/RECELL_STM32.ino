/*
 * RECELL-AI Firmware (Arduino IDE / STM32duino)
 * Target: STM32F411CEU6 (BlackPill)
 * Motor Driver: BTS7960
 * Sensors: I2C (INA219 / similar), IR Sensors, Limit Switches
 */

#include <ArduinoJson.h>
#include <Wire.h>
#include <INA226_WE.h>          // Library INA226
#include <Adafruit_MLX90614.h>  // Library Sensor Suhu Laser (IR Temp)
#include <Adafruit_MCP4725.h>   // Library DAC Eksternal

INA226_WE ina226 = INA226_WE(0x40);
Adafruit_MLX90614 mlx = Adafruit_MLX90614();
Adafruit_MCP4725 dac;

// --- KONFIGURASI PIN BARU ---

// 1. SENSORS & SWITCHES
const int PIN_LIMIT_DRAIN   = PB15; // Limit switch gerakan maks stepper Drain
const int PIN_IR_DRAIN      = PB14; // IR menghentikan baterai di Drain (PROX_1)
const int PIN_IR_BACKUP     = PB13; // IR cadangan
const int PIN_IR_SORTING    = PB12; // IR menghentikan baterai di Sorting (PROX_2)
const int PIN_LIMIT_SORTING = PA4;  // Limit switch gerakan maks stepper Sorting
const int PIN_EMERGENCY     = PB5;  // Emergency button

// 2. CONVEYOR (BTS 7960)
const int PIN_CONVEYOR_EN   = PA5; // ENABLE BTS 7960
const int PIN_CONVEYOR_RPWM = PA1; // R PWM BTS 7960 (Maju)
const int PIN_CONVEYOR_LPWM = PA2; // L PWM BTS 7960 (Mundur)

// 3. STEPPER 1 (DRAIN STATION / SENSOR PUSHER)
const int PIN_STP_DRAIN_DIR = PB0; // DIR STEPPER DRAIN STATION
const int PIN_STP_DRAIN_PUL = PB9; // PUL STEPPER DRAIN STATION
const int PIN_STP_DRAIN_EN  = PA7; // ENCODER/ENABLE STEPPER DRAIN STATION

// 4. STEPPER 2 (SORTING STATION / EJECTOR)
const int PIN_STP_SORT_DIR  = PA3; // DIR STEPPER SORTING STATION
const int PIN_STP_SORT_PUL  = PA8; // PUL STEPPER SORTING STATION
const int PIN_STP_SORT_EN   = PA6; // ENCODER/ENABLE STEPPER SORTING STATION

// 5. DAC & I2C
const int PIN_DAC_EN        = PB1; // ENCODER DAC (Logika nyala/mati beban)
// I2C SDA = PB7, SCL = PB6 (Gunakan Wire default Arduino)

// --- STATE MACHINE ---
enum SystemState {
  STATE_IDLE,
  STATE_WAIT_PROX_1,
  STATE_WAIT_PROX_2,
  STATE_EMERGENCY
};

SystemState currentState = STATE_IDLE;
int conveyorSpeed = 100; // Kecepatan BTS7960 (0-255)
bool i2cReady = false;

// --- PARAMETER PENGUKURAN SoH ---
// Selama beban DAC aktif, ambil DISCHARGE_SAMPLES sampel berjarak
// DISCHARGE_PERIOD_MS -> total ~2 detik. Tiap sampel di-stream ke Jetson
// sebagai DISCHARGE_SAMPLE (untuk live discharge curve) lalu dirata-rata
// jadi nilai v_load/i_load akhir.
const int DISCHARGE_SAMPLES   = 40;   // 40 x 50ms = ~2000ms beban
const int DISCHARGE_PERIOD_MS = 50;

// --- PARAMETER STEPPER ---
// Semua gerakan stepper SAMPAI LIMIT SWITCH (bukan step tetap). Tiap stepper
// punya 2 limit (ujung maju + home) diparalel di 1 pin. Logika robust: kalau
// start MENEMPEL limit (kasus mundur/home), carriage jalan dulu sampai limit
// LEPAS stabil STEPPER_REARM_STEPS step (anti-bounce) -> baru boleh berhenti
// saat limit lawan KENA (dikonfirmasi anti-noise). STEPPER_MAX_STEPS = pengaman
// supaya stepper tidak jalan tak terbatas bila limit gagal.
const int  STEPPER_PULSE_US      = 400;   // setengah-pulsa (us)
const long STEPPER_MAX_STEPS     = 25000; // ceiling pengaman 1 leg
const int  STEPPER_REARM_STEPS   = 40;    // limit harus LEPAS stabil sekian step
const int  LIMIT_CONFIRM_SAMPLES = 4;     // sampel LOW beruntun utk konfirmasi
const int  LIMIT_CONFIRM_US      = 200;   // jeda antar sampel konfirmasi

void setup() {
  Serial.begin(115200); 
  
  // Inisialisasi I2C (SDA=PB7, SCL=PB6 secara default pada Core STM32duino)
  Wire.begin();
  
  if (ina226.init()) {
    ina226.waitUntilConversionCompleted(); // Tunggu inisialisasi
    i2cReady = true;
  }
  
  mlx.begin();
  dac.begin(0x62); // Alamat I2C umum untuk MCP4725 (bisa juga 0x60)
  dac.setVoltage(0, false); // Pastikan load DAC 0 Volt di awal
  
  // Setup Sensor Pins
  pinMode(PIN_LIMIT_DRAIN, INPUT_PULLUP);
  pinMode(PIN_IR_DRAIN, INPUT_PULLUP);
  pinMode(PIN_IR_BACKUP, INPUT_PULLUP);
  pinMode(PIN_IR_SORTING, INPUT_PULLUP);
  pinMode(PIN_LIMIT_SORTING, INPUT_PULLUP);
  pinMode(PIN_EMERGENCY, INPUT_PULLUP);
  
  // Setup Conveyor BTS7960
  pinMode(PIN_CONVEYOR_EN, OUTPUT);
  pinMode(PIN_CONVEYOR_RPWM, OUTPUT);
  pinMode(PIN_CONVEYOR_LPWM, OUTPUT);
  digitalWrite(PIN_CONVEYOR_EN, HIGH); // Aktifkan driver
  
  // Setup Stepper Drain
  pinMode(PIN_STP_DRAIN_DIR, OUTPUT); 
  pinMode(PIN_STP_DRAIN_PUL, OUTPUT); 
  pinMode(PIN_STP_DRAIN_EN, OUTPUT);
  digitalWrite(PIN_STP_DRAIN_EN, HIGH); // Default Disable
  
  // Setup Stepper Sorting
  pinMode(PIN_STP_SORT_DIR, OUTPUT); 
  pinMode(PIN_STP_SORT_PUL, OUTPUT); 
  pinMode(PIN_STP_SORT_EN, OUTPUT);
  digitalWrite(PIN_STP_SORT_EN, HIGH); // Default Disable
  
  // Setup DAC
  pinMode(PIN_DAC_EN, OUTPUT);
  digitalWrite(PIN_DAC_EN, LOW); // DAC Mati agar tidak noise

  sendTelemetry(0, 0, "BOOT_OK");
}

void loop() {
  // Cek tombol Emergency secara real-time (Active Low)
  if (digitalRead(PIN_EMERGENCY) == LOW && currentState != STATE_EMERGENCY) {
    stopConveyor();
    currentState = STATE_EMERGENCY;
    sendTelemetry(0, 0, "EMERGENCY_STOP");
  }

  if (Serial.available() > 0) {
    String incomingStr = Serial.readStringUntil('\n');
    processCommand(incomingStr);
  }

  // --- NON-BLOCKING SENSOR CHECKS ---
  if (currentState == STATE_WAIT_PROX_1) {
    // IR Sensor biasanya mendeteksi halangan dengan output LOW
    if (digitalRead(PIN_IR_DRAIN) == LOW) {
      stopConveyor();
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "AT_PROX_1");
    }
  }
  
  if (currentState == STATE_WAIT_PROX_2) {
    if (digitalRead(PIN_IR_SORTING) == LOW) {
      stopConveyor();
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "AT_PROX_2");
    }
  }
}

void processCommand(String jsonStr) {
  if (currentState == STATE_EMERGENCY && jsonStr.indexOf("RESET") == -1) return; // Block commands if emergency

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, jsonStr);
  if (error) return;

  String cmd = doc["cmd"];

  if (cmd == "RESET") {
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "RESET_OK");
  }
  else if (cmd == "MOVE_TO_PROX_1") {
    startConveyorForward();
    currentState = STATE_WAIT_PROX_1;
  }
  else if (cmd == "APPLY_SENSOR_AND_MEASURE") {
    // 1. Dorong Sensor (Drain Station Stepper)
    moveStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_STP_DRAIN_EN, PIN_LIMIT_DRAIN, HIGH);

    // Suhu awal + tegangan OPEN-CIRCUIT (sebelum beban). v_resting WAJIB diukur
    // di sini supaya Jetson bisa hitung v_drop = v_resting - v_load (basis SoH).
    float tempPre  = mlx.readObjectTempC();
    float vResting = i2cReady ? ina226.getBusVoltage_V() : 4.2;

    // 2. Nyalakan beban DAC, lalu sampling + STREAM discharge curve selama ~2s.
    digitalWrite(PIN_DAC_EN, HIGH); // Nyalakan Enable DAC
    dac.setVoltage(4095, false);    // Beban maksimal via DAC I2C

    float v = 0.0, i = 0.0;
    float sumV = 0, sumI = 0;
    for (int j = 0; j < DISCHARGE_SAMPLES; j++) {
      float vt, it, tt;
      if (i2cReady) {
        vt = ina226.getBusVoltage_V();
        it = ina226.getCurrent_mA() / 1000.0;
        tt = mlx.readObjectTempC();
      } else {
        // Dummy bila modul I2C belum terpasang -- pipeline tetap jalan
        vt = 3.75; it = 1.50; tt = tempPre;
      }
      sumV += vt; sumI += it;
      sendDischargeSample((unsigned long)j * DISCHARGE_PERIOD_MS, vt, it, tt);
      delay(DISCHARGE_PERIOD_MS);
    }
    v = sumV / DISCHARGE_SAMPLES;
    i = sumI / DISCHARGE_SAMPLES;

    float tempPost  = mlx.readObjectTempC();
    float tempDelta = tempPost - tempPre;

    dac.setVoltage(0, false);       // Matikan Load DAC
    digitalWrite(PIN_DAC_EN, LOW);  // Matikan Enable DAC

    // 3. Tarik Sensor mundur SAMPAI limit home (bukan step tetap) -> posisi
    //    home selalu konsisten, tidak drift tiap siklus.
    moveStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_STP_DRAIN_EN, PIN_LIMIT_DRAIN, LOW);

    sendMeasurement(vResting, v, i, tempPre, tempPost, tempDelta, "MEASUREMENT_DONE");
  }
  else if (cmd == "MOVE_TO_PROX_2") {
    startConveyorForward();
    currentState = STATE_WAIT_PROX_2;
  }
  else if (cmd == "EJECT_A") {
    // Dorong ejector ke limit depan, lalu mundur SAMPAI limit home (bukan 2500
    // step tetap) -> ejector selalu balik tepat ke home, tidak drift.
    moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_STP_SORT_EN, PIN_LIMIT_SORTING, HIGH);
    moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_STP_SORT_EN, PIN_LIMIT_SORTING, LOW);
    sendTelemetry(0, 0, "EJECTED_A");
  }
  else if (cmd == "MOVE_TO_END") {
    startConveyorForward();
    delay(5000); // Biarkan maju selama 5 detik hingga baterai jatuh
    stopConveyor();
    sendTelemetry(0, 0, "DROPPED_B");
  }
  else if (cmd == "STOP_CONVEYOR") {
    stopConveyor();
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "STOPPED");
  }
}

// --- FUNGSI HELPER BTS7960 ---
void startConveyorForward() {
  digitalWrite(PIN_CONVEYOR_EN, HIGH);
  analogWrite(PIN_CONVEYOR_LPWM, 0);
  analogWrite(PIN_CONVEYOR_RPWM, conveyorSpeed);
}

void stopConveyor() {
  analogWrite(PIN_CONVEYOR_RPWM, 0);
  analogWrite(PIN_CONVEYOR_LPWM, 0);
}

// --- FUNGSI HELPER STEPPER ---
// Konfirmasi limit benar-benar LOW (debounce anti-noise/glitch).
bool limitConfirmed(int pinLimit) {
  for (int k = 0; k < LIMIT_CONFIRM_SAMPLES; k++) {
    delayMicroseconds(LIMIT_CONFIRM_US);
    if (digitalRead(pinLimit) != LOW) return false;
  }
  return true;
}

// Gerakkan stepper ke arah 'dir' SAMPAI limit switch kena (bukan step tetap).
// Robust untuk start menempel limit (kasus mundur/home): kalau limit sudah LOW
// saat mulai, carriage jalan dulu sampai limit LEPAS (HIGH) stabil
// STEPPER_REARM_STEPS step -> baru "armed", lalu berhenti saat limit lawan KENA
// (LOW terkonfirmasi). STEPPER_MAX_STEPS jadi pengaman bila limit gagal.
// SENYAP: tidak menulis ke Serial (Serial = kanal JSON ke Jetson).
void moveStepperUntilLimit(int pinStep, int pinDir, int pinEn, int pinLimit, int dir) {
  digitalWrite(pinEn, LOW);   // Enable driver (active LOW)
  digitalWrite(pinDir, dir);
  delayMicroseconds(20);      // settle arah

  bool startFree = (digitalRead(pinLimit) == HIGH);
  bool armed     = startFree;                          // start bebas -> langsung siap
  int  clearCnt  = startFree ? STEPPER_REARM_STEPS : 0;

  for (long i = 0; i < STEPPER_MAX_STEPS; i++) {
    if (digitalRead(PIN_EMERGENCY) == LOW) break;     // abort bila emergency

    if (digitalRead(pinLimit) == HIGH) {
      // limit lepas -- butuh stabil dulu baru dianggap benar-benar lepas
      if (clearCnt < STEPPER_REARM_STEPS) clearCnt++;
      if (clearCnt >= STEPPER_REARM_STEPS) armed = true;
    } else {
      // LOW: reset hitungan lepas; berhenti hanya kalau sudah armed + terkonfirmasi
      clearCnt = 0;
      if (armed && limitConfirmed(pinLimit)) break;
    }

    digitalWrite(pinStep, HIGH); delayMicroseconds(STEPPER_PULSE_US);
    digitalWrite(pinStep, LOW);  delayMicroseconds(STEPPER_PULSE_US);
  }
  digitalWrite(pinEn, HIGH);  // Disable driver
}

void sendTelemetry(float v, float i, const char* status) {
  sendTelemetryExt(v, i, 0.0, status);
}

void sendTelemetryExt(float v, float i, float tempDelta, const char* status) {
  StaticJsonDocument<200> doc;
  doc["volt"] = serialized(String(v, 3));
  doc["curr"] = serialized(String(i, 3));
  doc["temp_delta"] = serialized(String(tempDelta, 2));
  doc["status"] = status;
  serializeJson(doc, Serial);
  Serial.println();
}

// Hasil pengukuran lengkap -> dipakai Jetson untuk hitung v_drop, internal_R,
// dan fitur SoH (XGBoost). Field harus cocok dgn parser di main.py.
void sendMeasurement(float vResting, float v, float i,
                     float tempPre, float tempPost, float tempDelta,
                     const char* status) {
  StaticJsonDocument<256> doc;
  doc["volt"]       = serialized(String(v, 3));
  doc["curr"]       = serialized(String(i, 3));
  doc["v_resting"]  = serialized(String(vResting, 3));
  doc["temp_pre"]   = serialized(String(tempPre, 2));
  doc["temp_post"]  = serialized(String(tempPost, 2));
  doc["temp_delta"] = serialized(String(tempDelta, 2));
  doc["status"]     = status;
  serializeJson(doc, Serial);
  Serial.println();
}

// Satu titik kurva discharge (di-stream tiap sampel selama beban aktif).
void sendDischargeSample(unsigned long t_ms, float v, float i, float temp) {
  StaticJsonDocument<160> doc;
  doc["status"] = "DISCHARGE_SAMPLE";
  doc["t_ms"]   = t_ms;
  doc["volt"]   = serialized(String(v, 4));
  doc["curr"]   = serialized(String(i, 4));
  doc["temp"]   = serialized(String(temp, 2));
  serializeJson(doc, Serial);
  Serial.println();
}
