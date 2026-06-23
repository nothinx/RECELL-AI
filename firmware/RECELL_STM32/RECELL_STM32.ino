/*
 * RECELL-AI Firmware PRODUKSI v2 (Arduino IDE / STM32duino)
 * Target: STM32F411CEU6 (BlackPill)
 * Master = Jetson (kirim command JSON). Firmware = primitive gerakan teruji
 * yang diadopsi dari WORKFLOW_TEST (pin terkoreksi, DIR LOW=maju, return-to-home,
 * debounce limit, init INA226 benar). Protokol JSON identik dgn parser main.py.
 *
 * Serial: 115200 baud, line ending Newline (\n). Serial = kanal JSON -> semua
 * helper gerakan SENYAP (tidak menulis teks ke Serial).
 */

#include <ArduinoJson.h>
#include <Wire.h>
#include <INA226_WE.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MCP4725.h>

// --- I2C ALAMAT & SHUNT ---
const uint8_t ADDR_INA226   = 0x40;
const uint8_t ADDR_MCP4725  = 0x62;
const float   INA_SHUNT_OHM = 0.002;
const float   INA_MAX_AMP   = 10.0;

INA226_WE         ina226 = INA226_WE(ADDR_INA226);
Adafruit_MLX90614 mlx    = Adafruit_MLX90614();
Adafruit_MCP4725  dac;

// --- PIN (sumber kebenaran: WORKFLOW_TEST / wiring lapangan terkoreksi) ---
const int PIN_LIMIT_DRAIN   = PB15;
const int PIN_LIMIT_SORTING = PA4;
const int PIN_IR_DRAIN      = PB14; // PROX_1
const int PIN_IR_SORTING    = PB12; // PROX_2
const int PIN_IR_BACKUP     = PB13;
const int PIN_EMERGENCY     = PB5;

const int PIN_CONVEYOR_EN   = PA5;
const int PIN_CONVEYOR_RPWM = PA1; // maju
const int PIN_CONVEYOR_LPWM = PA2; // mundur

// Stepper: driver always-on (EN di-tie hardware; PA7/PA6 = input encoder, TIDAK dipakai).
const int PIN_STP_DRAIN_PUL = PA8;
const int PIN_STP_DRAIN_DIR = PA3;
const int PIN_STP_SORT_PUL  = PB9;
const int PIN_STP_SORT_DIR  = PB0;

const int PIN_DAC_GATE      = PB1;
const int PIN_I2C_SDA       = PB7;
const int PIN_I2C_SCL       = PB6;

// --- PARAMETER ---
// conveyorSpeed & stepPulseUs bisa diubah saat runtime via SET_CONFIG (panel
// kalibrasi F12 / tombol di layar) tanpa re-flash. Default konveyor diturunkan
// 100 -> 25 karena pada trial PWM 30 pun baterai over-shoot sensor IR.
int  conveyorSpeed               = 25;    // PWM 0-255
int  stepPulseUs                 = 50;    // setengah-pulsa stepper (us) target; makin besar makin pelan
// Ramp akselerasi stepper: mulai dari rampStartPulseUs (pelan, anti-stall) lalu
// turun bertahap ke stepPulseUs selama rampSteps step. Tanpa ramp, start langsung
// di stepPulseUs kecil bikin motor cuma berdengung/diam (penyebab STEP_TIMEOUT).
int  rampStartPulseUs            = 600;   // setengah-pulsa awal (pelan)
int  rampSteps                   = 300;   // panjang ramp (step) sampai mencapai target
const int  STEPPER_REARM_STEPS   = 40;    // limit harus LEPAS stabil sekian step
const int  LIMIT_CONFIRM_SAMPLES = 4;     // sampel LOW beruntun utk konfirmasi
const int  LIMIT_CONFIRM_US      = 200;   // jeda antar sampel konfirmasi
int  dischargeSamples            = 40;    // 40 x 50ms = ~2000ms beban (tunable)
int  dischargePeriodMs           = 50;    // (tunable)
uint16_t dacLoadValue            = 4095;  // beban maksimal (tunable)
int  ir2SettleMs                 = 0;     // delay lanjut konveyor setelah IR2 sblm stop (tunable)

// Mode diagnostik: saat aktif, broadcast snapshot semua sensor tiap DIAG_PERIOD_MS.
bool diagMode                    = false;
unsigned long lastDiagMs         = 0;
const unsigned long DIAG_PERIOD_MS = 200;
bool dacManualOn                 = false; // status beban DAC (utk telemetri diag)

// Heartbeat: denyut ~1Hz supaya Jetson bisa deteksi board hang/diam (beda dari
// kabel lepas). Tak dikirim saat diagMode (snapshot DIAG sudah jadi denyut).
unsigned long lastBeatMs         = 0;
const unsigned long BEAT_PERIOD_MS = 1000;
const unsigned long END_OF_LINE_MS = 5000;
const unsigned long STEPPER_TIMEOUT_MS = 10000; // stall guard: limit tak kunjung kena
const unsigned long PROX_TIMEOUT_MS    = 25000; // guard: IR tak terdeteksi (baterai nyangkut)
const unsigned long JOG_TIMEOUT_MS     = 10000; // auto-stop jog bila operator lupa Stop

// Arah DIR: LOW = maju ke limit, HIGH = mundur ke home.
const int DIR_FORWARD = LOW;
const int DIR_HOME    = HIGH;

enum SystemState { STATE_IDLE, STATE_WAIT_PROX_1, STATE_WAIT_PROX_2, STATE_EMERGENCY };
SystemState currentState = STATE_IDLE;
unsigned long waitStartMs = 0; // kapan masuk STATE_WAIT_PROX_* (untuk timeout)
unsigned long jogStopMs   = 0; // !=0 -> auto-stop konveyor jog pada waktu ini

bool inaReady = false, mlxReady = false, dacReady = false;

// ==========================================================================
void setup() {
  Serial.begin(115200);

  Wire.setSDA(PIN_I2C_SDA);
  Wire.setSCL(PIN_I2C_SCL);
  Wire.begin();
  initSensors();

  pinMode(PIN_LIMIT_DRAIN, INPUT_PULLUP);
  pinMode(PIN_LIMIT_SORTING, INPUT_PULLUP);
  pinMode(PIN_IR_DRAIN, INPUT_PULLUP);
  pinMode(PIN_IR_SORTING, INPUT_PULLUP);
  pinMode(PIN_IR_BACKUP, INPUT_PULLUP);
  pinMode(PIN_EMERGENCY, INPUT_PULLUP);

  pinMode(PIN_CONVEYOR_EN, OUTPUT);
  pinMode(PIN_CONVEYOR_RPWM, OUTPUT);
  pinMode(PIN_CONVEYOR_LPWM, OUTPUT);
  stopConveyor();

  pinMode(PIN_STP_DRAIN_PUL, OUTPUT);
  pinMode(PIN_STP_DRAIN_DIR, OUTPUT);
  pinMode(PIN_STP_SORT_PUL, OUTPUT);
  pinMode(PIN_STP_SORT_DIR, OUTPUT);
  digitalWrite(PIN_STP_DRAIN_PUL, LOW);
  digitalWrite(PIN_STP_SORT_PUL, LOW);

  pinMode(PIN_DAC_GATE, OUTPUT);
  digitalWrite(PIN_DAC_GATE, LOW);

  sendTelemetry(0, 0, "BOOT_OK");
}

void initSensors() {
  inaReady = ina226.init();
  if (inaReady) {
    ina226.setResistorRange(INA_SHUNT_OHM, INA_MAX_AMP); // WAJIB: tanpa ini arus salah
    ina226.setMeasureMode(INA226_CONTINUOUS);
  }
  mlxReady = mlx.begin();
  dacReady = dac.begin(ADDR_MCP4725);
  if (dacReady) dac.setVoltage(0, false);
}

// ==========================================================================
void loop() {
  emergencyActive(); // deteksi E-stop fisik real-time

  // Auto-stop jog: pengaman bila konveyor di-jog lalu Stop tak ditekan.
  if (jogStopMs && millis() > jogStopMs) {
    stopConveyor();              // juga me-reset jogStopMs
    sendTelemetry(0, 0, "STOPPED");
  }

  if (Serial.available() > 0) {
    String incomingStr = Serial.readStringUntil('\n');
    processCommand(incomingStr);
  }

  if (currentState == STATE_WAIT_PROX_1) {
    if (digitalRead(PIN_IR_DRAIN) == LOW) {
      stopConveyor();
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "AT_PROX_1");
    } else if (millis() - waitStartMs > PROX_TIMEOUT_MS) {
      stopConveyor();
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "STEP_TIMEOUT");
    }
  }
  if (currentState == STATE_WAIT_PROX_2) {
    if (digitalRead(PIN_IR_SORTING) == LOW) {
      // Lanjut sebentar (ir2SettleMs) supaya baterai pas di ejector, baru stop.
      if (ir2SettleMs > 0) {
        unsigned long s0 = millis();
        while (millis() - s0 < (unsigned long)ir2SettleMs) {
          if (emergencyActive()) return;
          delay(2);
        }
      }
      stopConveyor();
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "AT_PROX_2");
    } else if (millis() - waitStartMs > PROX_TIMEOUT_MS) {
      stopConveyor();
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "STEP_TIMEOUT");
    }
  }

  // Broadcast snapshot diagnostik saat mode diag aktif (panel kalibrasi terbuka).
  if (diagMode && millis() - lastDiagMs >= DIAG_PERIOD_MS) {
    lastDiagMs = millis();
    sendDiag();
  }

  // Heartbeat ~1Hz (kecuali diagMode yg sudah memancar). Jetson pakai ini utk
  // deteksi board hang (port terbuka tapi MCU diam).
  if (!diagMode && millis() - lastBeatMs >= BEAT_PERIOD_MS) {
    lastBeatMs = millis();
    sendTelemetry(0, 0, "HEARTBEAT");
  }
}

// Deteksi E-stop fisik. Kirim EMERGENCY_STOP sekali, matikan aktuator, set state.
bool emergencyActive() {
  if (digitalRead(PIN_EMERGENCY) == LOW) {
    if (currentState != STATE_EMERGENCY) {
      stopConveyor();
      safeShutdownLoad();
      currentState = STATE_EMERGENCY;
      sendTelemetry(0, 0, "EMERGENCY_STOP");
    }
    return true;
  }
  return false;
}

// ==========================================================================
void processCommand(String jsonStr) {
  StaticJsonDocument<200> doc;
  if (deserializeJson(doc, jsonStr)) return;
  String cmd = doc["cmd"];

  // Saat EMERGENCY, hanya RESET yang diterima.
  if (currentState == STATE_EMERGENCY && cmd != "RESET") return;

  if (cmd == "RESET") {
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "RESET_OK");
  }
  else if (cmd == "SET_CONFIG") {
    // Panel kalibrasi mengirim semua parameter motion + ukur (semua opsional).
    if (doc.containsKey("conveyor_speed"))
      conveyorSpeed = constrain((int)doc["conveyor_speed"], 0, 255);
    if (doc.containsKey("step_pulse_us"))
      stepPulseUs = constrain((int)doc["step_pulse_us"], 20, 5000);
    if (doc.containsKey("ramp_start_us"))
      rampStartPulseUs = constrain((int)doc["ramp_start_us"], 20, 5000);
    if (doc.containsKey("ramp_steps"))
      rampSteps = constrain((int)doc["ramp_steps"], 0, 5000);
    if (doc.containsKey("dac_load"))
      dacLoadValue = (uint16_t)constrain((int)doc["dac_load"], 0, 4095);
    if (doc.containsKey("discharge_samples"))
      dischargeSamples = constrain((int)doc["discharge_samples"], 1, 500);
    if (doc.containsKey("discharge_period"))
      dischargePeriodMs = constrain((int)doc["discharge_period"], 5, 1000);
    if (doc.containsKey("ir2_settle"))
      ir2SettleMs = constrain((int)doc["ir2_settle"], 0, 5000);
    sendTelemetry(conveyorSpeed, stepPulseUs, "CONFIG_OK");
  }
  else if (cmd == "JOG_FWD") {
    // Jalankan konveyor maju utk uji kecepatan saat setup. Auto-stop setelah
    // JOG_TIMEOUT_MS sebagai pengaman bila operator lupa menekan Stop.
    startConveyorForward();
    jogStopMs = millis() + JOG_TIMEOUT_MS;
    sendTelemetry(conveyorSpeed, 0, "JOGGING");
  }
  else if (cmd == "MOVE_TO_PROX_1") {
    startConveyorForward();
    waitStartMs = millis();
    currentState = STATE_WAIT_PROX_1;
  }
  else if (cmd == "APPLY_SENSOR_AND_MEASURE") {
    runMeasurement();
  }
  else if (cmd == "MOVE_TO_PROX_2") {
    startConveyorForward();
    waitStartMs = millis();
    currentState = STATE_WAIT_PROX_2;
  }
  else if (cmd == "EJECT_A") {
    if (!moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_LIMIT_SORTING, DIR_FORWARD)) return;
    if (!moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_LIMIT_SORTING, DIR_HOME)) return;
    sendTelemetry(0, 0, "EJECTED_A");
  }
  else if (cmd == "MOVE_TO_END") {
    startConveyorForward();
    unsigned long t0 = millis();
    while (millis() - t0 < END_OF_LINE_MS) {
      if (emergencyActive()) return;
      delay(5);
    }
    stopConveyor();
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "DROPPED_B");
  }
  else if (cmd == "STOP_CONVEYOR") {
    stopConveyor();
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "STOPPED");
  }
  // ---- DIAGNOSTIK / PANEL KALIBRASI ----------------------------------------
  else if (cmd == "START_DIAG") {
    diagMode = true;
    lastDiagMs = 0;                 // paksa snapshot pertama segera
    sendTelemetry(0, 0, "DIAG_ON");
  }
  else if (cmd == "STOP_DIAG") {
    diagMode = false;
    sendTelemetry(0, 0, "DIAG_OFF");
  }
  else if (cmd == "JOG_STEPPER") {
    // Jog mentah N step, tanpa limit. which=drain|sort, dir=fwd|rev.
    String which = doc["which"];
    String dir   = doc["dir"];
    bool sort = (which == "sort");
    int  dirVal = (dir == "rev") ? DIR_HOME : DIR_FORWARD;
    long steps = doc.containsKey("steps") ? (long)doc["steps"] : 200;
    int pul = sort ? PIN_STP_SORT_PUL : PIN_STP_DRAIN_PUL;
    int d   = sort ? PIN_STP_SORT_DIR : PIN_STP_DRAIN_DIR;
    jogStepperRaw(pul, d, dirVal, steps);
    sendTelemetry(0, 0, "JOG_DONE");
  }
  else if (cmd == "HOME_STEPPER") {
    // Dorong ke limit lalu mundur ke home (tanpa DAC). which=drain|sort.
    String which = doc["which"];
    bool sort = (which == "sort");
    int pul = sort ? PIN_STP_SORT_PUL : PIN_STP_DRAIN_PUL;
    int d   = sort ? PIN_STP_SORT_DIR : PIN_STP_DRAIN_DIR;
    int lim = sort ? PIN_LIMIT_SORTING : PIN_LIMIT_DRAIN;
    if (!moveStepperUntilLimit(pul, d, lim, DIR_FORWARD)) return;
    if (!moveStepperUntilLimit(pul, d, lim, DIR_HOME)) return;
    sendTelemetry(0, 0, "HOME_DONE");
  }
  else if (cmd == "CONVEYOR") {
    // Konveyor manual: dir=fwd|rev|stop. fwd pakai pengaman auto-stop jog.
    String dir = doc["dir"];
    if (dir == "fwd") {
      startConveyorForward();
      jogStopMs = millis() + JOG_TIMEOUT_MS;
      sendTelemetry(conveyorSpeed, 0, "JOGGING");
    } else if (dir == "rev") {
      startConveyorReverse();
      jogStopMs = millis() + JOG_TIMEOUT_MS;
      sendTelemetry(conveyorSpeed, 0, "JOGGING");
    } else {
      stopConveyor();
      sendTelemetry(0, 0, "STOPPED");
    }
  }
  else if (cmd == "DAC_LOAD") {
    // Beban DAC manual: on=1/0, value 0-4095 (default dacLoadValue).
    bool on = doc.containsKey("on") ? ((int)doc["on"] != 0) : false;
    if (on) {
      uint16_t val = doc.containsKey("value")
                     ? (uint16_t)constrain((int)doc["value"], 0, 4095) : dacLoadValue;
      digitalWrite(PIN_DAC_GATE, HIGH);
      if (dacReady) dac.setVoltage(val, false);
      dacManualOn = true;
    } else {
      safeShutdownLoad();
      dacManualOn = false;
    }
    sendTelemetry(0, 0, "DAC_SET");
  }
}

// --- Pengukuran SoH: push -> beban+stream discharge -> retract -------------
void runMeasurement() {
  // 1. Dorong sensor ke limit drain.
  if (!moveStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_LIMIT_DRAIN, DIR_FORWARD)) return;

  // 2. Baseline open-circuit (basis v_drop/internal_R di Jetson).
  float tempPre  = mlxReady ? mlx.readObjectTempC() : 25.0;
  float vResting = inaReady ? ina226.getBusVoltage_V() : 4.2;

  // 3. Nyalakan beban DAC, sampling + stream discharge curve ~2s.
  digitalWrite(PIN_DAC_GATE, HIGH);
  if (dacReady) dac.setVoltage(dacLoadValue, false);

  float sumV = 0, sumI = 0;
  for (int j = 0; j < dischargeSamples; j++) {
    if (emergencyActive()) { safeShutdownLoad(); return; }
    float vt, it, tt;
    if (inaReady) {
      vt = ina226.getBusVoltage_V();
      it = ina226.getCurrent_mA() / 1000.0;
      tt = mlxReady ? mlx.readObjectTempC() : tempPre;
    } else {
      vt = 3.75; it = 1.50; tt = tempPre; // dummy bila I2C belum terpasang
    }
    sumV += vt; sumI += it;
    sendDischargeSample((unsigned long)j * dischargePeriodMs, vt, it, tt);
    delay(dischargePeriodMs);
  }
  float v = sumV / dischargeSamples;
  float i = sumI / dischargeSamples;
  float tempPost  = mlxReady ? mlx.readObjectTempC() : tempPre;
  float tempDelta = tempPost - tempPre;

  safeShutdownLoad();

  // 4. Tarik sensor mundur ke home (konsisten, tidak drift).
  if (!moveStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_LIMIT_DRAIN, DIR_HOME)) return;

  sendMeasurement(vResting, v, i, tempPre, tempPost, tempDelta, "MEASUREMENT_DONE");
}

// ==========================================================================
// AKTUATOR
void startConveyorForward() {
  jogStopMs = 0; // gerakan normal membatalkan timer jog yang mungkin tersisa
  digitalWrite(PIN_CONVEYOR_EN, HIGH);
  analogWrite(PIN_CONVEYOR_LPWM, 0);
  // Soft-start: naikkan PWM bertahap agar belt tak menyentak & baterai tidak
  // over-shoot sensor IR. Durasi skala dgn target (~15ms/step, ~300ms @ PWM100).
  // ponytail: ramp tetap; jadikan parameter hanya bila trial menuntut.
  for (int pwm = 0; pwm < conveyorSpeed; pwm += 5) {
    if (emergencyActive()) return;   // emergencyActive() sudah stopConveyor()
    analogWrite(PIN_CONVEYOR_RPWM, pwm);
    delay(15);
  }
  analogWrite(PIN_CONVEYOR_RPWM, conveyorSpeed);
}

// Konveyor mundur (LPWM) untuk reposisi manual saat setup. Soft-start sama.
void startConveyorReverse() {
  jogStopMs = 0;
  digitalWrite(PIN_CONVEYOR_EN, HIGH);
  analogWrite(PIN_CONVEYOR_RPWM, 0);
  for (int pwm = 0; pwm < conveyorSpeed; pwm += 5) {
    if (emergencyActive()) return;
    analogWrite(PIN_CONVEYOR_LPWM, pwm);
    delay(15);
  }
  analogWrite(PIN_CONVEYOR_LPWM, conveyorSpeed);
}

void stopConveyor() {
  jogStopMs = 0;
  analogWrite(PIN_CONVEYOR_RPWM, 0);
  analogWrite(PIN_CONVEYOR_LPWM, 0);
  digitalWrite(PIN_CONVEYOR_EN, LOW);
}

void safeShutdownLoad() {
  if (dacReady) dac.setVoltage(0, false);
  digitalWrite(PIN_DAC_GATE, LOW);
}

// Konfirmasi limit benar-benar LOW (debounce anti-noise).
bool limitConfirmed(int pinLimit) {
  for (int k = 0; k < LIMIT_CONFIRM_SAMPLES; k++) {
    delayMicroseconds(LIMIT_CONFIRM_US);
    if (digitalRead(pinLimit) != LOW) return false;
  }
  return true;
}

// Lebar setengah-pulsa pada step ke-i dengan ramp akselerasi: mulai pelan
// (rampStartPulseUs) lalu turun linear ke stepPulseUs selama rampSteps step.
int rampPulseUs(long i) {
  if (rampSteps <= 0 || i >= rampSteps) return stepPulseUs;
  long span = (long)rampStartPulseUs - stepPulseUs;     // biasanya > 0 (start lebih lambat)
  return (int)(rampStartPulseUs - span * i / rampSteps);
}

// Satu langkah stepper dengan lebar pulsa terampa (dipakai bersama oleh
// moveStepperUntilLimit & jog mentah).
inline void stepPulse(int pinStep, long i) {
  int half = rampPulseUs(i);
  digitalWrite(pinStep, HIGH); delayMicroseconds(half);
  digitalWrite(pinStep, LOW);  delayMicroseconds(half);
}

// Gerakkan stepper ke arah 'dir' SAMPAI limit kena. Robust untuk start menempel
// limit: jalan dulu sampai limit LEPAS stabil STEPPER_REARM_STEPS step -> armed,
// baru berhenti saat limit lawan KENA terkonfirmasi. Tanpa ceiling step. SENYAP.
// Return true bila limit tercapai; false bila di-abort: E-stop fisik (STATE_EMERGENCY)
// ATAU stall-guard STEPPER_TIMEOUT_MS terlampaui -> pancarkan STEP_TIMEOUT, mesin IDLE.
bool moveStepperUntilLimit(int pinStep, int pinDir, int pinLimit, int dir) {
  digitalWrite(pinDir, dir);
  delayMicroseconds(20);

  bool startFree = (digitalRead(pinLimit) == HIGH);
  bool armed     = startFree;
  int  clearCnt  = startFree ? STEPPER_REARM_STEPS : 0;
  unsigned long t0 = millis();

  for (long i = 0; ; i++) {
    if (emergencyActive()) return false;

    if (millis() - t0 > STEPPER_TIMEOUT_MS) {
      // Limit tak kunjung kena (motor macet / limit gagal) -> fault lunak.
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "STEP_TIMEOUT");
      return false;
    }

    if (digitalRead(pinLimit) == HIGH) {
      if (clearCnt < STEPPER_REARM_STEPS) clearCnt++;
      if (clearCnt >= STEPPER_REARM_STEPS) armed = true;
    } else {
      clearCnt = 0;
      if (armed && limitConfirmed(pinLimit)) return true;
    }

    stepPulse(pinStep, i);
  }
}

// Jog MENTAH: gerak 'steps' step ke arah 'dir' TANPA peduli limit. Untuk diagnosa
// motor/driver terisolasi dari sensor limit. Abort-aware (E-stop). Pakai ramp.
void jogStepperRaw(int pinStep, int pinDir, int dir, long steps) {
  digitalWrite(pinDir, dir);
  delayMicroseconds(20);
  for (long i = 0; i < steps; i++) {
    if (emergencyActive()) return;
    stepPulse(pinStep, i);
  }
}

// ==========================================================================
// TELEMETRI JSON (field harus cocok dgn parser main.py)
void sendTelemetry(float v, float i, const char* status) {
  StaticJsonDocument<200> doc;
  doc["volt"]   = serialized(String(v, 3));
  doc["curr"]   = serialized(String(i, 3));
  doc["status"] = status;
  serializeJson(doc, Serial);
  Serial.println();
}

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

const char* stateName() {
  switch (currentState) {
    case STATE_WAIT_PROX_1: return "WAIT_PROX_1";
    case STATE_WAIT_PROX_2: return "WAIT_PROX_2";
    case STATE_EMERGENCY:   return "EMERGENCY";
    default:                return "IDLE";
  }
}

// Snapshot diagnostik: semua input digital, sensor I2C, state, config aktif.
// Sensor aktif LOW -> dilaporkan 1 saat aktif (objek/tertekan) supaya intuitif di UI.
void sendDiag() {
  StaticJsonDocument<768> doc;
  doc["status"] = "DIAG";
  doc["ir_d"]   = (digitalRead(PIN_IR_DRAIN)      == LOW) ? 1 : 0;
  doc["ir_s"]   = (digitalRead(PIN_IR_SORTING)    == LOW) ? 1 : 0;
  doc["ir_b"]   = (digitalRead(PIN_IR_BACKUP)     == LOW) ? 1 : 0;
  doc["lim_d"]  = (digitalRead(PIN_LIMIT_DRAIN)   == LOW) ? 1 : 0;
  doc["lim_s"]  = (digitalRead(PIN_LIMIT_SORTING) == LOW) ? 1 : 0;
  doc["emg"]    = (digitalRead(PIN_EMERGENCY)     == LOW) ? 1 : 0;
  doc["v"]      = serialized(String(inaReady ? ina226.getBusVoltage_V() : 0.0, 3));
  doc["i"]      = serialized(String(inaReady ? ina226.getCurrent_mA() / 1000.0 : 0.0, 3));
  doc["t_obj"]  = serialized(String(mlxReady ? mlx.readObjectTempC()  : 0.0, 1));
  doc["t_amb"]  = serialized(String(mlxReady ? mlx.readAmbientTempC() : 0.0, 1));
  JsonObject rdy = doc.createNestedObject("rdy");
  rdy["ina"] = inaReady ? 1 : 0;
  rdy["mlx"] = mlxReady ? 1 : 0;
  rdy["dac"] = dacReady ? 1 : 0;
  doc["st"]  = stateName();
  doc["dac"] = dacManualOn ? 1 : 0;
  JsonObject cfg = doc.createNestedObject("cfg");
  cfg["spd"]   = conveyorSpeed;
  cfg["pul"]   = stepPulseUs;
  cfg["ramp"]  = rampStartPulseUs;
  cfg["rstep"] = rampSteps;
  cfg["load"]  = dacLoadValue;
  cfg["dsmp"]  = dischargeSamples;
  cfg["dper"]  = dischargePeriodMs;
  cfg["ir2"]   = ir2SettleMs;
  serializeJson(doc, Serial);
  Serial.println();
}
