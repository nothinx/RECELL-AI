/*
 * ============================================================================
 *  RECELL-AI WORKFLOW TEST  (v1)
 *  Target MCU : STM32F411CEU6  (STM32duino core)
 *  Serial     : 115200 baud, line ending "Newline" / "NL"
 * ----------------------------------------------------------------------------
 *  Validasi alur SORTING penuh TANPA Jetson. Operator menggerakkan
 *  workflow langkah-demi-langkah pakai keyboard. Semua data (V, I, dT,
 *  durasi tiap step, grade manual) di-log sebagai satu baris CSV per
 *  siklus -> langsung copy-paste dari serial monitor ke file .csv untuk
 *  dipakai program otomatis & training model SoH.
 *
 *  ALUR SIKLUS:
 *    0. IDLE      -> ketik START
 *    1. AUTO      -> konveyor maju, otomatis stop saat IR1 (PB14) LOW
 *    2. ENTER     -> stepper DRAIN dorong ke LIMIT 1 (PB15)
 *    3. ENTER     -> measure SoH (DAC=4095, beban 2s, 10 sampel V/I, dT)
 *    4. ENTER     -> stepper DRAIN mundur 1000 step
 *    5. ENTER     -> konveyor maju lagi
 *    6. INPUT     -> ketik 1 (Grade A) atau 2 (Grade B/R)
 *    7a. ENTER    -> [Grade A] tunggu IR2 (PB12) -> stepper SORT push ke
 *                    LIMIT 2 (PA4) -> mundur sampai kena limit HOME
 *    7b. ENTER    -> [Grade B/R] konveyor jalan 5 detik -> stop
 *    8. AUTO      -> cetak baris CSV, counter++, balik ke IDLE
 *
 *  ABORT / EMERGENCY:
 *    - Tombol EMERGENCY (PB5 LOW)  -> stop konveyor + DAC + retract stepper
 *      (kalau sedang menempel limit drain) -> abort siklus.
 *    - Ketik ABORT di serial saat menunggu  -> sama dengan emergency.
 *    - Limit switch otomatis menghentikan stepper (logika "edge" supaya
 *      tetap bisa mundur saat carriage sudah menempel limit).
 *
 *  FORMAT LOG CSV (prefix "CSV," supaya gampang di-filter dari log lain):
 *    CSV,cycle_id,timestamp_ms,grade_manual,v_load_V,i_load_A,
 *        temp_init_C,temp_final_C,temp_delta_C,
 *        t_to_ir1_ms,t_push_ms,t_measure_ms,t_retract_ms,
 *        t_to_ir2_or_end_ms,abort_reason
 *  Header dicetak sekali saat boot supaya satu file paste = lengkap.
 *
 *  Catatan pinout (sesuai CSV "Konfirmasi Pinout Final"):
 *    - PA7 & PA6 adalah INPUT encoder, bukan ENABLE. Driver stepper
 *      diasumsikan SELALU AKTIF (pin ENABLE di-tie di hardware).
 * ============================================================================
 */

#include <Wire.h>
#include <INA226_WE.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MCP4725.h>

// --------------------------------------------------------------------------
//  KONFIGURASI PIN  (identik dengan HARDWARE_TEST.ino)
// --------------------------------------------------------------------------
const int PIN_LIMIT_DRAIN   = PB15;
const int PIN_LIMIT_SORTING = PA4;
const int PIN_IR_DRAIN      = PB14;
const int PIN_IR_SORTING    = PB12;
const int PIN_IR_BACKUP     = PB13;
const int PIN_EMERGENCY     = PB5;

const int PIN_CONVEYOR_EN   = PA5;
const int PIN_CONVEYOR_RPWM = PA1;
const int PIN_CONVEYOR_LPWM = PA2;

// CATATAN: stepper drain & sorting tertukar di wiring fisik vs label CSV.
// Pin yang DI-CSV ditandai "PUL SORT" (PA8) sebenarnya menggerakkan motor
// drain station, dan sebaliknya. Mapping di bawah sudah diluruskan supaya
// nama variabel sesuai motor FISIKAL.
// Verifikasi dulu lewat STEPPER_TEST sebelum produksi.
const int PIN_STP_DRAIN_PUL = PA8;   // CSV: "PUL SORT"  -> fisik: drain motor
const int PIN_STP_DRAIN_DIR = PA3;   // CSV: "DIR SORT"  -> fisik: drain motor
const int PIN_STP_SORT_PUL  = PB9;   // CSV: "PUL DRAIN" -> fisik: sort motor
const int PIN_STP_SORT_DIR  = PB0;   // CSV: "DIR DRAIN" -> fisik: sort motor

const int PIN_DAC_GATE      = PB1;

const int PIN_I2C_SDA       = PB7;
const int PIN_I2C_SCL       = PB6;

const uint8_t ADDR_INA226   = 0x40;
const uint8_t ADDR_MLX90614 = 0x5A;
const uint8_t ADDR_MCP4725  = 0x62;

const float INA_SHUNT_OHM   = 0.002;
const float INA_MAX_AMP     = 10.0;

// --------------------------------------------------------------------------
//  PARAMETER WORKFLOW  (samakan dengan firmware produksi RECELL_STM32.ino)
// --------------------------------------------------------------------------
const int  CONVEYOR_SPEED       = 30;     // PWM 0-255 (pelan utk testing)
const int  STEPPER_PULSE_US     = 50;     // setengah-pulsa (us)
const int  RELEASE_CONFIRM_STEPS = 40;    // limit harus LEPAS (HIGH) stabil sekian step
                                          // sebelum boleh berhenti di limit lawan (anti-bounce)
const uint16_t DAC_LOAD_VALUE   = 4095;   // beban maksimal
const unsigned long LOAD_HOLD_MS = 2000;  // tahan beban
const int  SOH_SAMPLE_COUNT     = 10;     // sampel V/I
const int  SOH_SAMPLE_DELAY_MS  = 10;
const unsigned long END_OF_LINE_MS = 5000; // timer Grade B/R
const unsigned long IR2_SETTLE_MS  = 0;  // Grade A: jalan terus 0.2s setelah IR2 baru stop
                                           // (supaya baterai pas di ejector, tidak mepet ujung)

// -- Proteksi stepper: debounce confirm-hit limit switch -------------------
// Saat carriage menyentuh limit (LOW), pin dibaca ulang LIMIT_CONFIRM_SAMPLES
// kali (jeda LIMIT_CONFIRM_US). Hanya jika SEMUA LOW -> dianggap benar kena.
// Mencegah glitch/noise satu sampel menghentikan stepper di tengah jalan.
const int  LIMIT_CONFIRM_SAMPLES = 4;
const int  LIMIT_CONFIRM_US      = 200;

// -- Mode AUTO: grade diputuskan otomatis dari tegangan berbeban ------------
// v_load >= GRADE_A_MIN_V -> Grade A, selain itu Grade B/R.
const float GRADE_A_MIN_V        = 3.60;
const unsigned long AUTO_STEP_PAUSE_MS = 400;  // jeda antar-step di mode AUTO

// --------------------------------------------------------------------------
//  STATE GLOBAL
// --------------------------------------------------------------------------
INA226_WE          ina226 = INA226_WE(ADDR_INA226);
Adafruit_MLX90614  mlx     = Adafruit_MLX90614();
Adafruit_MCP4725   dac;

bool inaReady = false;
bool mlxReady = false;
bool dacReady = false;

uint32_t cycle_counter = 0;

// Data satu siklus -- diisi step-by-step, dicetak sekali di akhir
struct CycleData {
  uint32_t    cycle_id;
  uint32_t    timestamp_start_ms;
  const char* mode;             // "MANUAL" atau "AUTO"
  char        grade_manual;     // 'A', 'B', atau '?' jika abort
  const char* grade_source;     // "MANUAL" atau "AUTO_THRESH"
  float       v_open_V;         // tegangan open-circuit (sebelum beban)
  float       v_load_V;
  float       i_load_A;
  float       r_internal_mOhm;  // (v_open - v_load) / i_load, indikator SoH
  float       temp_init_C;
  float       temp_final_C;
  float       temp_delta_C;
  uint32_t    t_to_ir1_ms;
  uint32_t    t_push_ms;
  uint32_t    t_measure_ms;
  uint32_t    t_retract_ms;
  uint32_t    t_to_ir2_or_end_ms;
  const char* abort_reason;     // "OK" atau alasan abort
};

void resetCycleData(CycleData& d) {
  d.cycle_id            = ++cycle_counter;
  d.timestamp_start_ms  = millis();
  d.mode                = "MANUAL";
  d.grade_manual        = '?';
  d.grade_source        = "MANUAL";
  d.v_open_V            = 0.0;
  d.v_load_V            = 0.0;
  d.i_load_A            = 0.0;
  d.r_internal_mOhm     = 0.0;
  d.temp_init_C         = 0.0;
  d.temp_final_C        = 0.0;
  d.temp_delta_C        = 0.0;
  d.t_to_ir1_ms         = 0;
  d.t_push_ms           = 0;
  d.t_measure_ms        = 0;
  d.t_retract_ms        = 0;
  d.t_to_ir2_or_end_ms  = 0;
  d.abort_reason        = "OK";
}

// ==========================================================================
//  SETUP
// ==========================================================================
void setup() {
  Serial.begin(115200);
  delay(800);

  pinMode(PIN_LIMIT_DRAIN,   INPUT_PULLUP);
  pinMode(PIN_LIMIT_SORTING, INPUT_PULLUP);
  pinMode(PIN_IR_DRAIN,      INPUT_PULLUP);
  pinMode(PIN_IR_SORTING,    INPUT_PULLUP);
  pinMode(PIN_IR_BACKUP,     INPUT_PULLUP);
  pinMode(PIN_EMERGENCY,     INPUT_PULLUP);

  pinMode(PIN_CONVEYOR_EN,   OUTPUT);
  pinMode(PIN_CONVEYOR_RPWM, OUTPUT);
  pinMode(PIN_CONVEYOR_LPWM, OUTPUT);
  stopConveyor();

  pinMode(PIN_STP_DRAIN_PUL, OUTPUT);
  pinMode(PIN_STP_DRAIN_DIR, OUTPUT);
  pinMode(PIN_STP_SORT_PUL,  OUTPUT);
  pinMode(PIN_STP_SORT_DIR,  OUTPUT);
  digitalWrite(PIN_STP_DRAIN_PUL, LOW);
  digitalWrite(PIN_STP_SORT_PUL,  LOW);

  pinMode(PIN_DAC_GATE, OUTPUT);
  digitalWrite(PIN_DAC_GATE, LOW);

  Wire.setSDA(PIN_I2C_SDA);
  Wire.setSCL(PIN_I2C_SCL);
  Wire.begin();
  initSensors();

  printBanner();
  printCSVHeader();
  printIdlePrompt();
}

// ==========================================================================
//  LOOP UTAMA -- tunggu START, lalu jalankan satu siklus
// ==========================================================================
void loop() {
  if (!Serial.available()) return;

  String line = readLineTrimmed();
  if (line.length() == 0) { printIdlePrompt(); return; }

  if (line.equalsIgnoreCase("START")) {
    runOneCycle(false);
    printIdlePrompt();
  } else if (line.equalsIgnoreCase("AUTO") || line.startsWith("AUTO ") || line.startsWith("auto ")) {
    // "AUTO" = 1 siklus otomatis, "AUTO n" = n siklus berturut
    long n = 1;
    int sp = line.indexOf(' ');
    if (sp > 0) { long v = line.substring(sp + 1).toInt(); if (v > 0) n = v; }
    Serial.print(F("[AUTO] menjalankan ")); Serial.print(n); Serial.println(F(" siklus otomatis..."));
    for (long k = 0; k < n; k++) {
      const char* r = runOneCycle(true);
      if (r && strcmp(r, "OK") != 0) {
        Serial.print(F("[AUTO] dihentikan dini di siklus ")); Serial.print(k + 1);
        Serial.print(F(" -> ")); Serial.println(r);
        break;
      }
    }
    printIdlePrompt();
  } else if (line.equalsIgnoreCase("STATUS")) {
    printSensorBlock();
    printIdlePrompt();
  } else if (line.equalsIgnoreCase("HELP") || line == "?") {
    printHelp();
    printIdlePrompt();
  } else {
    Serial.print(F("[!] Perintah tidak dikenal: ")); Serial.println(line);
    printIdlePrompt();
  }
}

// ==========================================================================
//  CYCLE RUNNER -- linear, top-down. Setiap step return reason (nullptr=OK).
// ==========================================================================
// Bungkus 1 siklus: setup data, jalankan, cetak CSV + ringkasan. Return reason.
const char* runOneCycle(bool autoMode) {
  CycleData d;
  resetCycleData(d);
  d.mode = autoMode ? "AUTO" : "MANUAL";
  runCycle(d, autoMode);
  logStepSnapshot("AKHIR");
  printCSVRow(d);
  Serial.println();
  Serial.print(F("[CYCLE ")); Serial.print(d.cycle_id);
  Serial.print(F(" SELESAI -- ")); Serial.print(d.abort_reason); Serial.println(F("]"));
  return d.abort_reason;
}

void runCycle(CycleData& d, bool autoMode) {
  Serial.println();
  Serial.print(F("=========== MULAI CYCLE ")); Serial.print(d.cycle_id);
  Serial.print(F("  [")); Serial.print(d.mode); Serial.println(F("] ==========="));
  logStepSnapshot("AWAL");

  const char* reason = nullptr;

  // -------- STEP 1: konveyor maju otomatis sampai IR1 -------------------
  Serial.println(F("[STEP 1] Konveyor maju, menunggu IR Drain (PB14)..."));
  logStepSnapshot("STEP1");
  unsigned long t0 = millis();
  startConveyorForward();
  reason = pollUntilIRDetected(PIN_IR_DRAIN, "IR Drain");
  stopConveyor();
  d.t_to_ir1_ms = millis() - t0;
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 1] OK. Baterai di drain station. Durasi="));
  Serial.print(d.t_to_ir1_ms); Serial.println(F(" ms"));

  // -------- STEP 2: push stepper drain ke limit -------------------------
  reason = gate(autoMode, F("[STEP 2] Tekan ENTER untuk DORONG stepper drain ke limit (atau ABORT)"));
  if (reason) { d.abort_reason = reason; return; }
  t0 = millis();
  reason = pushStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR,
                                 PIN_LIMIT_DRAIN, LOW, "DRAIN");  // DIR LOW = maju ke limit
  d.t_push_ms = millis() - t0;
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 2] OK. Limit drain tersentuh. Durasi="));
  Serial.print(d.t_push_ms); Serial.println(F(" ms"));

  // -------- STEP 3: measure SoH -----------------------------------------
  reason = gate(autoMode, F("[STEP 3] Tekan ENTER untuk UKUR SoH (DAC=4095, beban 2s)"));
  if (reason) { d.abort_reason = reason; safeShutdownLoad(); return; }
  t0 = millis();
  reason = measureSoH(d);
  d.t_measure_ms = millis() - t0;
  safeShutdownLoad();  // pastikan DAC mati apapun yg terjadi
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 3] OK. Vopen=")); Serial.print(d.v_open_V, 3);
  Serial.print(F("V  Vload=")); Serial.print(d.v_load_V, 3);
  Serial.print(F("V  I=")); Serial.print(d.i_load_A, 3);
  Serial.print(F("A  Rint=")); Serial.print(d.r_internal_mOhm, 1);
  Serial.print(F("mOhm  dT=")); Serial.print(d.temp_delta_C, 2);
  Serial.print(F("C  Durasi=")); Serial.print(d.t_measure_ms); Serial.println(F(" ms"));

  // -------- STEP 4: retract stepper drain -------------------------------
  reason = gate(autoMode, F("[STEP 4] Tekan ENTER untuk TARIK stepper drain mundur ke limit (home)"));
  if (reason) { d.abort_reason = reason; return; }
  t0 = millis();
  // Mundur sampai kena limit ujung lain (pin sama, 2 limit paralel). DIR HIGH =
  // mundur. Carriage mulai dari posisi nempel limit maju -> logika 'armed'
  // menunggu pin BEBAS dulu, baru berhenti saat menyentuh limit home.
  reason = pushStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR,
                                 PIN_LIMIT_DRAIN, HIGH, "DRAIN-back");
  d.t_retract_ms = millis() - t0;
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 4] OK. Stepper drain di limit home. Durasi="));
  Serial.print(d.t_retract_ms); Serial.println(F(" ms"));

  // -------- STEP 5: keputusan grade (SETELAH ukur + retract) ------------
  char grade;
  if (autoMode) {
    // AUTO: putuskan dari tegangan berbeban vs ambang.
    grade = (d.v_load_V >= GRADE_A_MIN_V) ? 'A' : 'B';
    d.grade_source = "AUTO_THRESH";
    Serial.print(F("[STEP 5] AUTO grade dari v_load=")); Serial.print(d.v_load_V, 3);
    Serial.print(F("V (ambang ")); Serial.print(GRADE_A_MIN_V, 2);
    Serial.print(F("V) -> Grade ")); Serial.println(grade);
  } else {
    Serial.println(F("[STEP 5] Ukur & retract selesai."));
    Serial.println(F("        Ketik 1 = Grade A (eject)  atau  2 = Grade B/R (end-of-line)"));
    grade = waitForGrade();
    if (grade == 0) {
      stopConveyor();
      d.abort_reason = "ABORT_AT_GRADE_DECISION";
      return;
    }
    d.grade_source = "MANUAL";
    Serial.print(F("[STEP 5] Grade dipilih: ")); Serial.println(grade);
  }
  d.grade_manual = grade;

  // -------- STEP 6: jalankan konveyor & sortir sesuai grade -------------
  // t_to_ir2_or_end_ms dihitung dari konveyor mulai jalan di sini -> total
  // transit time menuju IR2/end (berguna kalibrasi durasi konveyor otomatis).
  reason = gate(autoMode, F("[STEP 6] Tekan ENTER untuk jalankan konveyor & sortir"));
  if (reason) { d.abort_reason = reason; return; }
  startConveyorForward();
  unsigned long t_conveyor_restart = millis();
  Serial.println(F("[STEP 6] Konveyor maju..."));

  if (grade == 'A') {
    Serial.println(F("[STEP 6A] Menunggu IR Sorting (PB12)..."));
    reason = pollUntilIRDetected(PIN_IR_SORTING, "IR Sorting");
    if (reason) { stopConveyor(); d.abort_reason = reason; return; }

    // Jeda IR2_SETTLE_MS: konveyor TETAP jalan sebentar supaya baterai maju ke
    // posisi ejector yang benar (tadi terlalu mepet -> nabrak ujung) baru stop.
    Serial.print(F("[STEP 6A] IR2 terdeteksi, lanjut ")); Serial.print(IR2_SETTLE_MS);
    Serial.println(F(" ms baru stop..."));
    reason = sleepAbortable(IR2_SETTLE_MS);
    stopConveyor();
    d.t_to_ir2_or_end_ms = millis() - t_conveyor_restart;
    if (reason) { d.abort_reason = reason; return; }
    Serial.print(F("[STEP 6A] Di sorting station. Durasi konveyor->IR2(+settle) = "));
    Serial.print(d.t_to_ir2_or_end_ms); Serial.println(F(" ms"));

    reason = gate(autoMode, F("[STEP 6A] Tekan ENTER untuk EJECT Grade A"));
    if (reason) { d.abort_reason = reason; return; }

    reason = pushStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR,
                                   PIN_LIMIT_SORTING, LOW, "SORTING");  // DIR LOW = maju ke limit
    if (reason) { d.abort_reason = reason; return; }
    // Mundur sampai kena limit HOME. Sorting punya 2 limit switch (depan +
    // home) diparalel di PA4, sama seperti drain -> ejector SELALU balik tepat
    // ke home & tidak drift tiap siklus. (Dulu mundur 2500 step fixed: kalau
    // lemparan maju > 2500 step, ejector berhenti sebelum sampai home.)
    reason = pushStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR,
                                   PIN_LIMIT_SORTING, HIGH, "SORTING-back");  // DIR HIGH = mundur
    if (reason) { d.abort_reason = reason; return; }
    Serial.println(F("[STEP 6A] OK. Grade A ter-eject & ejector balik ke home."));
  } else { // grade == 'B'
    Serial.print(F("[STEP 6B] Konveyor jalan ")); Serial.print(END_OF_LINE_MS);
    Serial.println(F(" ms menuju end-of-line..."));
    reason = sleepAbortable(END_OF_LINE_MS);
    stopConveyor();
    d.t_to_ir2_or_end_ms = millis() - t_conveyor_restart;
    if (reason) { d.abort_reason = reason; return; }
    Serial.print(F("[STEP 6B] OK. Baterai jatuh di end-of-line. Durasi konveyor->end = "));
    Serial.print(d.t_to_ir2_or_end_ms); Serial.println(F(" ms"));
  }
}

// ==========================================================================
//  HELPER: MENUNGGU INPUT
// ==========================================================================
String readLineTrimmed() {
  String s = Serial.readStringUntil('\n');
  s.trim();
  return s;
}

void flushSerial() { while (Serial.available()) Serial.read(); }

// Tunggu ENTER. Kalau user ketik ABORT (case-insensitive) -> abort.
// Tombol emergency juga diabaikan. Return nullptr jika OK.
const char* waitEnter(const __FlashStringHelper* prompt) {
  Serial.println();
  Serial.println(prompt);
  Serial.print(F(" > "));
  flushSerial();
  while (true) {
    if (digitalRead(PIN_EMERGENCY) == LOW) {
      stopConveyor();
      return "EMERGENCY_BUTTON";
    }
    if (Serial.available()) {
      String s = readLineTrimmed();
      if (s.equalsIgnoreCase("ABORT")) return "ABORT_USER";
      return nullptr;  // ENTER kosong atau apapun -> lanjut
    }
    delay(5);
  }
}

// Gate antar-step. MANUAL: tunggu ENTER. AUTO: jeda kecil, tetap abort-aware.
const char* gate(bool autoMode, const __FlashStringHelper* prompt) {
  if (!autoMode) return waitEnter(prompt);
  Serial.println();
  Serial.print(F("[AUTO] ")); Serial.println(prompt);
  return sleepAbortable(AUTO_STEP_PAUSE_MS);
}

// Snapshot ringkas semua sensor untuk logging per-step.
void logStepSnapshot(const char* tag) {
  Serial.print(F("  .snap[")); Serial.print(tag); Serial.print(F("] "));
  Serial.print(F("LimDrain=")); Serial.print(digitalRead(PIN_LIMIT_DRAIN)   == LOW ? F("HIT")   : F("free"));
  Serial.print(F(" LimSort="));  Serial.print(digitalRead(PIN_LIMIT_SORTING) == LOW ? F("HIT")   : F("free"));
  Serial.print(F(" IR1="));      Serial.print(digitalRead(PIN_IR_DRAIN)      == LOW ? F("obj")   : F("-"));
  Serial.print(F(" IR2="));      Serial.print(digitalRead(PIN_IR_SORTING)    == LOW ? F("obj")   : F("-"));
  Serial.print(F(" EMG="));      Serial.print(digitalRead(PIN_EMERGENCY)     == LOW ? F("PRESS") : F("ok"));
  if (inaReady) {
    Serial.print(F(" V=")); Serial.print(ina226.getBusVoltage_V(), 3);
    Serial.print(F(" I=")); Serial.print(ina226.getCurrent_mA(), 0); Serial.print(F("mA"));
  }
  if (mlxReady) { Serial.print(F(" T=")); Serial.print(mlx.readObjectTempC(), 1); Serial.print(F("C")); }
  Serial.println();
}

// Konfirmasi limit benar-benar LOW (debounce anti-noise/glitch).
bool limitConfirmed(int limitPin) {
  for (int k = 0; k < LIMIT_CONFIRM_SAMPLES; k++) {
    delayMicroseconds(LIMIT_CONFIRM_US);
    if (digitalRead(limitPin) != LOW) return false;
  }
  return true;
}

// Tunggu user ketik '1' atau '2'. Return 'A', 'B', atau 0 jika abort.
char waitForGrade() {
  flushSerial();
  while (true) {
    if (digitalRead(PIN_EMERGENCY) == LOW) {
      stopConveyor();
      return 0;
    }
    if (Serial.available()) {
      String s = readLineTrimmed();
      if (s.length() == 0) continue;
      if (s.equalsIgnoreCase("ABORT")) return 0;
      char c = s.charAt(0);
      if (c == '1') return 'A';
      if (c == '2') return 'B';
      Serial.print(F("[!] Hanya 1 atau 2. Diterima: ")); Serial.println(s);
    }
    delay(5);
  }
}

// Poll sensor IR (active LOW) sampai terdeteksi. Abort-aware.
const char* pollUntilIRDetected(int pin, const char* name) {
  while (digitalRead(pin) != LOW) {
    if (digitalRead(PIN_EMERGENCY) == LOW) return "EMERGENCY_BUTTON";
    if (Serial.available()) {
      String s = readLineTrimmed();
      if (s.equalsIgnoreCase("ABORT")) return "ABORT_USER";
      // input lain diabaikan saat polling
    }
    delay(2);
  }
  return nullptr;
}

// Sleep ms millisecond tapi tetap responsif terhadap abort.
const char* sleepAbortable(unsigned long ms) {
  unsigned long t0 = millis();
  while (millis() - t0 < ms) {
    if (digitalRead(PIN_EMERGENCY) == LOW) return "EMERGENCY_BUTTON";
    if (Serial.available()) {
      String s = readLineTrimmed();
      if (s.equalsIgnoreCase("ABORT")) return "ABORT_USER";
    }
    delay(5);
  }
  return nullptr;
}

// ==========================================================================
//  HELPER: AKTUATOR
// ==========================================================================
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

// Gerakkan stepper ke arah 'dir' sampai limit switch KENA.
// Pola robust untuk start menempel limit:
//   1. Kalau start di limit (LOW), jalan dulu sampai limit LEPAS (HIGH) dan
//      stabil RELEASE_CONFIRM_STEPS step -> baru "armed".
//   2. Setelah armed, berhenti saat limit KENA lagi (LOW terkonfirmasi).
//   Kalau start sudah bebas, langsung armed.
// Debounce "lepas" mencegah bounce di titik awal dianggap sudah-lepas-lalu-kena
// (yang dulu bikin retract berhenti di ~0 step / "tidak bisa mundur").
// Tanpa batas step: berhenti hanya via EMERGENCY / ABORT / limit kena.
const char* pushStepperUntilLimit(int pulPin, int dirPin, int limitPin,
                                  int dir, const char* name) {
  Serial.print(F("  [STP ")); Serial.print(name); Serial.println(F("] cari limit..."));
  logStepSnapshot(name);
  digitalWrite(dirPin, dir);
  delayMicroseconds(20);

  bool startFree = (digitalRead(limitPin) == HIGH);
  bool armed     = startFree;                              // start bebas -> langsung siap
  int  clearCnt  = startFree ? RELEASE_CONFIRM_STEPS : 0;
  if (!startFree)
    Serial.println(F("    start MENEMPEL limit -> jalan sampai limit lepas dulu..."));

  for (long i = 0; ; i++) {
    if (digitalRead(PIN_EMERGENCY) == LOW) return "EMERGENCY_BUTTON";
    if ((i & 0x3F) == 0 && Serial.available()) {
      String s = readLineTrimmed();
      if (s.equalsIgnoreCase("ABORT")) return "ABORT_USER";
    }

    if (digitalRead(limitPin) == HIGH) {
      // limit lepas/hilang -- butuh stabil baru dianggap benar-benar lepas
      if (clearCnt < RELEASE_CONFIRM_STEPS) clearCnt++;
      if (clearCnt >= RELEASE_CONFIRM_STEPS && !armed) {
        armed = true;
        Serial.print(F("    limit LEPAS @ step ")); Serial.print(i + 1);
        Serial.println(F(" -> lanjut cari limit lawan"));
      }
    } else {
      // LOW: limit kena. reset hitungan lepas; berhenti hanya kalau sudah armed.
      clearCnt = 0;
      if (armed && limitConfirmed(limitPin)) {
        Serial.print(F("  [STP ")); Serial.print(name);
        Serial.print(F("] limit KENA terkonfirmasi @ step ")); Serial.println(i + 1);
        return nullptr;  // sukses
      }
    }

    digitalWrite(pulPin, HIGH); delayMicroseconds(STEPPER_PULSE_US);
    digitalWrite(pulPin, LOW);  delayMicroseconds(STEPPER_PULSE_US);
  }
}

// ==========================================================================
//  HELPER: PENGUKURAN SoH  (sama dengan APPLY_SENSOR_AND_MEASURE di produksi)
// ==========================================================================
const char* measureSoH(CycleData& d) {
  if (!inaReady || !mlxReady || !dacReady) {
    Serial.println(F("  [WARN] Sensor I2C tidak lengkap -- pakai dummy bila perlu."));
  }

  d.temp_init_C = mlxReady ? mlx.readObjectTempC() : 0.0;

  // Tegangan open-circuit (sebelum beban) -> basis hitung R internal.
  d.v_open_V = inaReady ? ina226.getBusVoltage_V() : 3.85;

  digitalWrite(PIN_DAC_GATE, HIGH);
  if (dacReady) dac.setVoltage(DAC_LOAD_VALUE, false);
  Serial.print(F("  [DAC] Beban ")); Serial.print(DAC_LOAD_VALUE);
  Serial.print(F("/4095, tahan ")); Serial.print(LOAD_HOLD_MS); Serial.println(F(" ms"));

  // Tahan beban -- tetap abort-aware
  const char* abort_r = sleepAbortable(LOAD_HOLD_MS);
  if (abort_r) { return abort_r; }

  // Sampling
  if (inaReady) {
    float sumV = 0, sumI = 0;
    for (int j = 0; j < SOH_SAMPLE_COUNT; j++) {
      sumV += ina226.getBusVoltage_V();
      sumI += ina226.getCurrent_mA() / 1000.0f;
      delay(SOH_SAMPLE_DELAY_MS);
    }
    d.v_load_V = sumV / SOH_SAMPLE_COUNT;
    d.i_load_A = sumI / SOH_SAMPLE_COUNT;
  } else {
    d.v_load_V = 3.75;  // dummy fallback supaya pipeline tetap jalan tanpa INA
    d.i_load_A = 1.50;
  }

  d.temp_final_C = mlxReady ? mlx.readObjectTempC() : 0.0;
  d.temp_delta_C = d.temp_final_C - d.temp_init_C;

  // Resistansi internal kasar (mOhm): (Vopen - Vload) / Iload. Hindari bagi nol.
  d.r_internal_mOhm = (d.i_load_A > 0.05f)
      ? (d.v_open_V - d.v_load_V) / d.i_load_A * 1000.0f
      : 0.0f;

  return nullptr;
}

// ==========================================================================
//  HELPER: LOG & PROMPT
// ==========================================================================
void printBanner() {
  Serial.println();
  Serial.println(F("============================================="));
  Serial.println(F("   RECELL-AI WORKFLOW TEST  (v1)"));
  Serial.println(F("   MCU: STM32F411CEU6  |  Baud: 115200"));
  Serial.println(F("============================================="));
  Serial.print  (F("   I2C: INA226=")); Serial.print(inaReady ? F("OK") : F("FAIL"));
  Serial.print  (F("  MLX90614="));     Serial.print(mlxReady ? F("OK") : F("FAIL"));
  Serial.print  (F("  MCP4725="));      Serial.println(dacReady ? F("OK") : F("FAIL"));
}

void printHelp() {
  Serial.println();
  Serial.println(F("Perintah saat IDLE:"));
  Serial.println(F("  START   - 1 siklus MANUAL (konfirmasi ENTER tiap step)"));
  Serial.println(F("  AUTO    - 1 siklus OTOMATIS (tanpa ENTER; grade dari ambang V)"));
  Serial.println(F("  AUTO n  - jalankan n siklus otomatis berturut"));
  Serial.println(F("  STATUS  - cetak pembacaan semua sensor"));
  Serial.println(F("  HELP    - tampilkan bantuan"));
  Serial.println(F("Selama siklus:"));
  Serial.println(F("  ENTER   - lanjut ke step berikutnya"));
  Serial.println(F("  ABORT   - batalkan siklus (sama dgn tombol EMERGENCY)"));
  Serial.println(F("Saat ditanya grade:"));
  Serial.println(F("  1 = Grade A (eject)   2 = Grade B/R (end-of-line)"));
}

void printIdlePrompt() {
  Serial.println();
  Serial.print(F("[IDLE] Cycle berikutnya = #")); Serial.print(cycle_counter + 1);
  Serial.println(F(". Ketik START / AUTO / AUTO n / STATUS / HELP."));
  Serial.print(F(" > "));
}

// Header CSV -- dicetak sekali saat boot
void printCSVHeader() {
  Serial.println();
  Serial.println(F(
    "CSV_HEADER,cycle_id,timestamp_ms,mode,grade_manual,grade_source,"
    "v_open_V,v_load_V,i_load_A,r_internal_mOhm,"
    "temp_init_C,temp_final_C,temp_delta_C,"
    "t_to_ir1_ms,t_push_ms,t_measure_ms,t_retract_ms,"
    "t_to_ir2_or_end_ms,abort_reason"));
}

void printCSVRow(const CycleData& d) {
  Serial.print(F("CSV,"));
  Serial.print(d.cycle_id);             Serial.print(',');
  Serial.print(d.timestamp_start_ms);   Serial.print(',');
  Serial.print(d.mode);                 Serial.print(',');
  Serial.print(d.grade_manual);         Serial.print(',');
  Serial.print(d.grade_source);         Serial.print(',');
  Serial.print(d.v_open_V, 3);          Serial.print(',');
  Serial.print(d.v_load_V, 3);          Serial.print(',');
  Serial.print(d.i_load_A, 3);          Serial.print(',');
  Serial.print(d.r_internal_mOhm, 1);   Serial.print(',');
  Serial.print(d.temp_init_C, 2);       Serial.print(',');
  Serial.print(d.temp_final_C, 2);      Serial.print(',');
  Serial.print(d.temp_delta_C, 2);      Serial.print(',');
  Serial.print(d.t_to_ir1_ms);          Serial.print(',');
  Serial.print(d.t_push_ms);            Serial.print(',');
  Serial.print(d.t_measure_ms);         Serial.print(',');
  Serial.print(d.t_retract_ms);         Serial.print(',');
  Serial.print(d.t_to_ir2_or_end_ms);   Serial.print(',');
  Serial.println(d.abort_reason);
}

// Cetak status semua sensor (perintah STATUS saat idle)
void printSensorBlock() {
  Serial.println(F("\n.... STATUS SENSOR ........................."));
  Serial.print(F("Emergency (PB5)   : ")); Serial.println(digitalRead(PIN_EMERGENCY) == LOW ? F("DITEKAN") : F("AMAN"));
  Serial.print(F("Limit Drain (PB15): ")); Serial.println(digitalRead(PIN_LIMIT_DRAIN) == LOW ? F("TERSENTUH") : F("BEBAS"));
  Serial.print(F("Limit Sort  (PA4) : ")); Serial.println(digitalRead(PIN_LIMIT_SORTING) == LOW ? F("TERSENTUH") : F("BEBAS"));
  Serial.print(F("IR Drain  (PB14)  : ")); Serial.println(digitalRead(PIN_IR_DRAIN) == LOW ? F("ADA OBJEK") : F("KOSONG"));
  Serial.print(F("IR Sort   (PB12)  : ")); Serial.println(digitalRead(PIN_IR_SORTING) == LOW ? F("ADA OBJEK") : F("KOSONG"));
  Serial.print(F("IR Backup (PB13)  : ")); Serial.println(digitalRead(PIN_IR_BACKUP) == LOW ? F("ADA OBJEK") : F("KOSONG"));
  if (inaReady) {
    Serial.print(F("INA226 V          : ")); Serial.print(ina226.getBusVoltage_V(), 3); Serial.println(F(" V"));
    Serial.print(F("INA226 I          : ")); Serial.print(ina226.getCurrent_mA(), 1);   Serial.println(F(" mA"));
  } else Serial.println(F("INA226            : TIDAK TERDETEKSI"));
  if (mlxReady) {
    Serial.print(F("MLX90614 Obj      : ")); Serial.print(mlx.readObjectTempC(), 2);    Serial.println(F(" C"));
    Serial.print(F("MLX90614 Amb      : ")); Serial.print(mlx.readAmbientTempC(), 2);   Serial.println(F(" C"));
  } else Serial.println(F("MLX90614          : TIDAK TERDETEKSI"));
}

// ==========================================================================
//  INISIALISASI SENSOR
// ==========================================================================
void initSensors() {
  inaReady = ina226.init();
  if (inaReady) {
    ina226.setResistorRange(INA_SHUNT_OHM, INA_MAX_AMP);
    ina226.setMeasureMode(INA226_CONTINUOUS);
  }
  mlxReady = mlx.begin();
  dacReady = dac.begin(ADDR_MCP4725);
  if (dacReady) dac.setVoltage(0, false);
}
