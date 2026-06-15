# RECELL Firmware v2 + GUI Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tulis ulang firmware produksi `RECELL_STM32.ino` agar memakai mekanik gerakan teruji dari WORKFLOW_TEST (pin terkoreksi, arah DIR, return-to-home, debounce limit, init INA226 benar) sambil mempertahankan protokol JSON yang sudah dipahami GUI, lalu tutup celah recovery emergency di `main.py`.

**Architecture:** Jetson (`main.py`) tetap master yang mengorkestrasi siklus & memutuskan grade (YOLO+XGBoost). STM32 jadi kumpulan primitive gerakan blocking yang dipanggil via perintah JSON. Sebuah test regresi Python mengunci kontrak command/status agar kedua sisi tetap sinkron.

**Tech Stack:** STM32duino (Arduino C++) untuk firmware; Python 3 + pytest untuk test kontrak protokol; library firmware: ArduinoJson, INA226_WE, Adafruit_MLX90614, Adafruit_MCP4725, Wire.

---

## File Structure

- **Create:** `tests/test_protocol_sync.py` — test regresi yang memverifikasi tiap command yang dikirim Jetson ditangani firmware, tiap status yang ditunggu Jetson dipancarkan firmware, dan field `MEASUREMENT_DONE`/`DISCHARGE_SAMPLE` cocok di kedua sisi. Satu tanggung jawab: penjaga kontrak protokol.
- **Rewrite:** `firmware/RECELL_STM32/RECELL_STM32.ino` — firmware produksi v2 (mekanik WORKFLOW_TEST + protokol JSON).
- **Modify:** `jetson/src/main.py` — kirim `RESET` di awal `run_automated_cycle()` untuk pulih dari E-stop.

Catatan: firmware tidak punya unit test runtime (butuh hardware). Verifikasinya = kompilasi (`arduino-cli`, best-effort di mesin ini) + test kontrak protokol berbasis sumber + smoke `--sim`.

---

## Task 1: Test kontrak sinkronisasi protokol

**Files:**
- Create: `tests/test_protocol_sync.py`

- [ ] **Step 1: Tulis test yang gagal**

Buat `tests/test_protocol_sync.py`:

```python
"""Regresi kontrak protokol Jetson <-> STM32.

Mencegah salah satu sisi me-rename command/status/field tanpa sisi lain ikut.
Hanya pakai stdlib supaya bisa jalan di lingkungan minim (tanpa pytest pun bisa
via blok __main__ di bawah).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW = (ROOT / "firmware" / "RECELL_STM32" / "RECELL_STM32.ino").read_text(encoding="utf-8")
MAIN = (ROOT / "jetson" / "src" / "main.py").read_text(encoding="utf-8")

# --- Kontrak kanonik -------------------------------------------------------
COMMANDS = [
    "RESET", "MOVE_TO_PROX_1", "APPLY_SENSOR_AND_MEASURE",
    "MOVE_TO_PROX_2", "EJECT_A", "MOVE_TO_END", "STOP_CONVEYOR",
]
# Status yang dipancarkan firmware (semua), dan subset yang ditindaklanjuti Jetson.
STATUSES_EMITTED = [
    "BOOT_OK", "AT_PROX_1", "AT_PROX_2", "DISCHARGE_SAMPLE", "MEASUREMENT_DONE",
    "EJECTED_A", "DROPPED_B", "STOPPED", "RESET_OK", "EMERGENCY_STOP",
]
STATUSES_CONSUMED = [
    "MEASUREMENT_DONE", "DISCHARGE_SAMPLE", "AT_PROX_1", "AT_PROX_2",
    "EJECTED_A", "DROPPED_B", "EMERGENCY_STOP",
]
MEASUREMENT_FIELDS = ["volt", "curr", "v_resting", "temp_pre", "temp_post", "temp_delta"]
DISCHARGE_FIELDS = ["t_ms", "volt", "curr", "temp"]


def test_every_command_handled_by_firmware():
    for c in COMMANDS:
        assert re.search(rf'cmd\s*==\s*"{c}"', FW), f"firmware tak menangani command {c}"


def test_every_command_sent_by_jetson():
    for c in COMMANDS:
        assert re.search(rf'send_command\(\s*"{c}"', MAIN), f"main.py tak pernah kirim {c}"


def test_firmware_emits_all_statuses():
    for s in STATUSES_EMITTED:
        assert f'"{s}"' in FW, f"firmware tak memancarkan status {s}"


def test_jetson_consumes_expected_statuses():
    for s in STATUSES_CONSUMED:
        assert f'"{s}"' in MAIN, f"main.py tak menangani status {s}"


def test_measurement_fields_match_both_sides():
    for f in MEASUREMENT_FIELDS:
        assert f'"{f}"' in FW, f"firmware MEASUREMENT_DONE tak punya field {f}"
        assert f'"{f}"' in MAIN, f"main.py tak membaca field {f}"


def test_discharge_fields_match_both_sides():
    for f in DISCHARGE_FIELDS:
        assert f'"{f}"' in FW, f"firmware DISCHARGE_SAMPLE tak punya field {f}"
        assert f'"{f}"' in MAIN, f"main.py tak membaca field {f}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("OK semua kontrak protokol sinkron")
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL pada bagian RESET**

Run: `python -m pytest tests/test_protocol_sync.py -v`
(atau tanpa pytest: `python tests/test_protocol_sync.py`)

Expected: `test_every_command_sent_by_jetson` **FAIL** dengan "main.py tak pernah kirim RESET"
(karena Task 3 belum menambahkan `send_command("RESET")`). Test lain mungkin juga belum
hijau sampai firmware ditulis ulang di Task 2 — itu wajar; test ini hijau penuh di akhir Task 3.

- [ ] **Step 3: Commit**

```bash
git add tests/test_protocol_sync.py
git commit -m "test(protocol): add Jetson<->STM32 contract sync regression"
```

---

## Task 2: Tulis ulang firmware `RECELL_STM32.ino` (mekanik WORKFLOW_TEST)

**Files:**
- Rewrite: `firmware/RECELL_STM32/RECELL_STM32.ino`

- [ ] **Step 1: Tulis isi firmware baru (timpa seluruh file)**

Tulis `firmware/RECELL_STM32/RECELL_STM32.ino` dengan isi PERSIS berikut:

```cpp
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
const int  CONVEYOR_SPEED        = 100;   // PWM 0-255 (produksi)
const int  STEPPER_PULSE_US      = 50;    // setengah-pulsa (us)
const int  STEPPER_REARM_STEPS   = 40;    // limit harus LEPAS stabil sekian step
const int  LIMIT_CONFIRM_SAMPLES = 4;     // sampel LOW beruntun utk konfirmasi
const int  LIMIT_CONFIRM_US      = 200;   // jeda antar sampel konfirmasi
const int  DISCHARGE_SAMPLES     = 40;    // 40 x 50ms = ~2000ms beban
const int  DISCHARGE_PERIOD_MS   = 50;
const uint16_t DAC_LOAD_VALUE    = 4095;  // beban maksimal
const unsigned long END_OF_LINE_MS = 5000;

// Arah DIR: LOW = maju ke limit, HIGH = mundur ke home.
const int DIR_FORWARD = LOW;
const int DIR_HOME    = HIGH;

enum SystemState { STATE_IDLE, STATE_WAIT_PROX_1, STATE_WAIT_PROX_2, STATE_EMERGENCY };
SystemState currentState = STATE_IDLE;

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

  if (Serial.available() > 0) {
    String incomingStr = Serial.readStringUntil('\n');
    processCommand(incomingStr);
  }

  if (currentState == STATE_WAIT_PROX_1 && digitalRead(PIN_IR_DRAIN) == LOW) {
    stopConveyor();
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "AT_PROX_1");
  }
  if (currentState == STATE_WAIT_PROX_2 && digitalRead(PIN_IR_SORTING) == LOW) {
    stopConveyor();
    currentState = STATE_IDLE;
    sendTelemetry(0, 0, "AT_PROX_2");
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
  else if (cmd == "MOVE_TO_PROX_1") {
    startConveyorForward();
    currentState = STATE_WAIT_PROX_1;
  }
  else if (cmd == "APPLY_SENSOR_AND_MEASURE") {
    runMeasurement();
  }
  else if (cmd == "MOVE_TO_PROX_2") {
    startConveyorForward();
    currentState = STATE_WAIT_PROX_2;
  }
  else if (cmd == "EJECT_A") {
    moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_LIMIT_SORTING, DIR_FORWARD);
    moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_LIMIT_SORTING, DIR_HOME);
    if (currentState != STATE_EMERGENCY) sendTelemetry(0, 0, "EJECTED_A");
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
}

// --- Pengukuran SoH: push -> beban+stream discharge -> retract -------------
void runMeasurement() {
  // 1. Dorong sensor ke limit drain.
  moveStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_LIMIT_DRAIN, DIR_FORWARD);
  if (currentState == STATE_EMERGENCY) return;

  // 2. Baseline open-circuit (basis v_drop/internal_R di Jetson).
  float tempPre  = mlxReady ? mlx.readObjectTempC() : 25.0;
  float vResting = inaReady ? ina226.getBusVoltage_V() : 4.2;

  // 3. Nyalakan beban DAC, sampling + stream discharge curve ~2s.
  digitalWrite(PIN_DAC_GATE, HIGH);
  if (dacReady) dac.setVoltage(DAC_LOAD_VALUE, false);

  float sumV = 0, sumI = 0;
  for (int j = 0; j < DISCHARGE_SAMPLES; j++) {
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
    sendDischargeSample((unsigned long)j * DISCHARGE_PERIOD_MS, vt, it, tt);
    delay(DISCHARGE_PERIOD_MS);
  }
  float v = sumV / DISCHARGE_SAMPLES;
  float i = sumI / DISCHARGE_SAMPLES;
  float tempPost  = mlxReady ? mlx.readObjectTempC() : tempPre;
  float tempDelta = tempPost - tempPre;

  safeShutdownLoad();

  // 4. Tarik sensor mundur ke home (konsisten, tidak drift).
  moveStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_LIMIT_DRAIN, DIR_HOME);
  if (currentState == STATE_EMERGENCY) return;

  sendMeasurement(vResting, v, i, tempPre, tempPost, tempDelta, "MEASUREMENT_DONE");
}

// ==========================================================================
// AKTUATOR
void startConveyorForward() {
  digitalWrite(PIN_CONVEYOR_EN, HIGH);
  analogWrite(PIN_CONVEYOR_LPWM, 0);
  analogWrite(PIN_CONVEYOR_RPWM, CONVEYOR_SPEED);
}

void stopConveyor() {
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

// Gerakkan stepper ke arah 'dir' SAMPAI limit kena. Robust untuk start menempel
// limit: jalan dulu sampai limit LEPAS stabil STEPPER_REARM_STEPS step -> armed,
// baru berhenti saat limit lawan KENA terkonfirmasi. Tanpa ceiling step. SENYAP.
// Abort bila E-stop fisik (set STATE_EMERGENCY via emergencyActive()).
void moveStepperUntilLimit(int pinStep, int pinDir, int pinLimit, int dir) {
  digitalWrite(pinDir, dir);
  delayMicroseconds(20);

  bool startFree = (digitalRead(pinLimit) == HIGH);
  bool armed     = startFree;
  int  clearCnt  = startFree ? STEPPER_REARM_STEPS : 0;

  for (long i = 0; ; i++) {
    if (emergencyActive()) return;

    if (digitalRead(pinLimit) == HIGH) {
      if (clearCnt < STEPPER_REARM_STEPS) clearCnt++;
      if (clearCnt >= STEPPER_REARM_STEPS) armed = true;
    } else {
      clearCnt = 0;
      if (armed && limitConfirmed(pinLimit)) return;
    }

    digitalWrite(pinStep, HIGH); delayMicroseconds(STEPPER_PULSE_US);
    digitalWrite(pinStep, LOW);  delayMicroseconds(STEPPER_PULSE_US);
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
```

- [ ] **Step 2: Kompilasi firmware (best-effort di mesin ini)**

Run: `arduino-cli compile --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE firmware/RECELL_STM32`
Expected: "Sketch uses ... bytes" tanpa error.
Jika `arduino-cli` tidak terpasang di mesin ini: lewati & tandai untuk dikompilasi di mesin
flashing (Arduino IDE). Catat di hasil bahwa kompilasi belum diverifikasi otomatis.

- [ ] **Step 3: Jalankan test kontrak — sisi firmware harus hijau**

Run: `python -m pytest tests/test_protocol_sync.py -v`
Expected: `test_every_command_handled_by_firmware`, `test_firmware_emits_all_statuses`,
`test_measurement_fields_match_both_sides`, `test_discharge_fields_match_both_sides` **PASS**.
`test_every_command_sent_by_jetson` masih **FAIL** pada RESET (diperbaiki di Task 3).

- [ ] **Step 4: Commit**

```bash
git add firmware/RECELL_STM32/RECELL_STM32.ino
git commit -m "feat(firmware): rewrite production firmware on WORKFLOW_TEST mechanics

Adopsi pin terkoreksi, DIR LOW=maju, return-to-home + debounce limit tanpa
ceiling, init INA226 setResistorRange (perbaiki pembacaan arus), measurement
abort-aware terhadap E-stop. Protokol JSON tidak berubah."
```

---

## Task 3: Auto-RESET di `main.py` untuk pulih dari E-stop

**Files:**
- Modify: `jetson/src/main.py` (dalam `run_automated_cycle`, setelah `self.grade_decision = None`)

- [ ] **Step 1: Tambah pengiriman RESET di awal siklus**

Di `jetson/src/main.py`, temukan blok ini di `run_automated_cycle`:

```python
        self.abort_cycle = False  # clear any previous abort
        # Reset grade so UI shows TESTING state cleanly
        self.grade_decision = None

        DATA_DIR.mkdir(parents=True, exist_ok=True)
```

Ubah menjadi (sisipkan pengiriman RESET):

```python
        self.abort_cycle = False  # clear any previous abort
        # Reset grade so UI shows TESTING state cleanly
        self.grade_decision = None

        # Clear any latched hardware E-stop on the STM32 so a cycle started after
        # an emergency doesn't hang on a silently-dropped command. Fire-and-forget:
        # firmware replies RESET_OK (not awaited). If the physical button is still
        # held, firmware re-enters EMERGENCY immediately.
        self.send_command("RESET")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Jalankan seluruh test kontrak — harus hijau penuh**

Run: `python -m pytest tests/test_protocol_sync.py -v`
Expected: **semua** test PASS, termasuk `test_every_command_sent_by_jetson`.

- [ ] **Step 3: Smoke test simulasi (protokol tidak rusak)**

Run: `python -c "import sys; sys.path.insert(0, 'jetson/src'); from main import RecellMaster; m = RecellMaster(simulate=True, mock_ai=True); m.run_automated_cycle(); print('SIM CYCLE OK')"`
Expected: berakhir dengan `SIM CYCLE OK` tanpa exception (akan tercetak log siklus + `[Simulate-TX] {"cmd": "RESET"}` di awal).

- [ ] **Step 4: Commit**

```bash
git add jetson/src/main.py
git commit -m "fix(jetson): send RESET at cycle start to recover from hardware E-stop"
```

---

## Self-Review (hasil)

**Spec coverage (Spec A):**
- §3 mekanik WORKFLOW_TEST (pin/DIR/return-to-home/debounce/pulse/INA init) → Task 2 firmware.
- §4 streaming discharge dipertahankan → `runMeasurement()` di Task 2.
- §5 kontrak command/status/field tidak berubah → dikunci test Task 1.
- §6a recovery deadlock → Task 3 auto-RESET; §6b measure abort-aware → `runMeasurement()` cek `emergencyActive()` tiap sampel.
- §7 perubahan main.py minimal → Task 3 hanya 1 sisipan.

**Placeholder scan:** tidak ada TBD/TODO; semua langkah punya kode & perintah konkret.

**Type/name consistency:** `emergencyActive()`, `moveStepperUntilLimit()`, `safeShutdownLoad()`,
`runMeasurement()`, `sendMeasurement()`, `sendDischargeSample()`, `sendTelemetry()`, konstanta
`DIR_FORWARD/DIR_HOME`, status & command string konsisten antara firmware, test, dan main.py.

**Catatan caveat (diterima, bukan gap):** STOP GUI tidak menghentikan perintah blocking; safety = PB5 fisik (Spec A §2). Tidak butuh task.
