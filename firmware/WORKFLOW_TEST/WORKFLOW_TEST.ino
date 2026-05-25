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
 *                    LIMIT 2 (PA4) -> mundur 2500 step
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
const int  STEPPER_PULSE_US     = 400;    // setengah-pulsa
const long STEPPER_MAX_TO_LIMIT = 5000;   // batas aman push-to-limit
const long STEPPER_RETRACT_DRAIN = 1000;  // mundur sensor drain
const long STEPPER_RETRACT_SORT  = 2500;  // mundur ejector sorting
const uint16_t DAC_LOAD_VALUE   = 4095;   // beban maksimal
const unsigned long LOAD_HOLD_MS = 2000;  // tahan beban
const int  SOH_SAMPLE_COUNT     = 10;     // sampel V/I
const int  SOH_SAMPLE_DELAY_MS  = 10;
const unsigned long END_OF_LINE_MS = 5000; // timer Grade B/R

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
  char        grade_manual;     // 'A', 'B', atau '?' jika abort
  float       v_load_V;
  float       i_load_A;
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
  d.grade_manual        = '?';
  d.v_load_V            = 0.0;
  d.i_load_A            = 0.0;
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
    CycleData d;
    resetCycleData(d);
    runCycle(d);
    printCSVRow(d);
    Serial.println();
    Serial.print(F("[CYCLE ")); Serial.print(d.cycle_id);
    Serial.print(F(" SELESAI -- ")); Serial.print(d.abort_reason); Serial.println(F("]"));
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
void runCycle(CycleData& d) {
  Serial.println();
  Serial.print(F("=========== MULAI CYCLE ")); Serial.print(d.cycle_id);
  Serial.println(F(" ==========="));

  const char* reason = nullptr;

  // -------- STEP 1: konveyor maju otomatis sampai IR1 -------------------
  Serial.println(F("[STEP 1] Konveyor maju, menunggu IR Drain (PB14)..."));
  unsigned long t0 = millis();
  startConveyorForward();
  reason = pollUntilIRDetected(PIN_IR_DRAIN, "IR Drain");
  stopConveyor();
  d.t_to_ir1_ms = millis() - t0;
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 1] OK. Baterai di drain station. Durasi="));
  Serial.print(d.t_to_ir1_ms); Serial.println(F(" ms"));

  // -------- STEP 2: push stepper drain ke limit -------------------------
  reason = waitEnter(F("[STEP 2] Tekan ENTER untuk DORONG stepper drain ke limit (atau ABORT)"));
  if (reason) { d.abort_reason = reason; return; }
  t0 = millis();
  reason = pushStepperUntilLimit(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR,
                                 PIN_LIMIT_DRAIN, LOW, "DRAIN");  // DIR LOW = maju ke limit
  d.t_push_ms = millis() - t0;
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 2] OK. Limit drain tersentuh. Durasi="));
  Serial.print(d.t_push_ms); Serial.println(F(" ms"));

  // -------- STEP 3: measure SoH -----------------------------------------
  reason = waitEnter(F("[STEP 3] Tekan ENTER untuk UKUR SoH (DAC=4095, beban 2s)"));
  if (reason) { d.abort_reason = reason; safeShutdownLoad(); return; }
  t0 = millis();
  reason = measureSoH(d);
  d.t_measure_ms = millis() - t0;
  safeShutdownLoad();  // pastikan DAC mati apapun yg terjadi
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 3] OK. V=")); Serial.print(d.v_load_V, 3);
  Serial.print(F("V  I=")); Serial.print(d.i_load_A, 3);
  Serial.print(F("A  dT=")); Serial.print(d.temp_delta_C, 2);
  Serial.print(F("C  Durasi=")); Serial.print(d.t_measure_ms); Serial.println(F(" ms"));

  // -------- STEP 4: retract stepper drain -------------------------------
  reason = waitEnter(F("[STEP 4] Tekan ENTER untuk TARIK stepper drain mundur"));
  if (reason) { d.abort_reason = reason; return; }
  t0 = millis();
  reason = moveStepperSteps(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR,
                            STEPPER_RETRACT_DRAIN, HIGH, "DRAIN");  // DIR HIGH = mundur
  d.t_retract_ms = millis() - t0;
  if (reason) { d.abort_reason = reason; return; }
  Serial.print(F("[STEP 4] OK. Stepper drain mundur. Durasi="));
  Serial.print(d.t_retract_ms); Serial.println(F(" ms"));

  // -------- STEP 5: konveyor jalan lagi ---------------------------------
  reason = waitEnter(F("[STEP 5] Tekan ENTER untuk LANJUTKAN konveyor"));
  if (reason) { d.abort_reason = reason; return; }
  startConveyorForward();
  unsigned long t_conveyor_restart = millis();   // basis t_to_ir2_or_end_ms
  Serial.println(F("[STEP 5] Konveyor maju..."));

  // -------- STEP 6: tunggu keputusan grade ------------------------------
  Serial.println(F("[STEP 6] Ketik 1 = Grade A (eject)  atau  2 = Grade B/R (end-of-line)"));
  char grade = waitForGrade();
  if (grade == 0) {
    stopConveyor();
    d.abort_reason = "ABORT_AT_GRADE_DECISION";
    return;
  }
  d.grade_manual = grade;
  Serial.print(F("[STEP 6] Grade dipilih: ")); Serial.println(grade);

  // -------- STEP 7a / 7b: eksekusi sortir -------------------------------
  // t_to_ir2_or_end_ms dihitung dari saat konveyor restart (step 5),
  // bukan dari awal step 7, supaya benar-benar mencerminkan total transit
  // time -- berguna untuk kalibrasi durasi konveyor di firmware otomatis.
  if (grade == 'A') {
    Serial.println(F("[STEP 7A] Menunggu IR Sorting (PB12)..."));
    reason = pollUntilIRDetected(PIN_IR_SORTING, "IR Sorting");
    stopConveyor();
    d.t_to_ir2_or_end_ms = millis() - t_conveyor_restart;
    if (reason) { d.abort_reason = reason; return; }
    Serial.print(F("[STEP 7A] Di sorting station. Durasi konveyor restart->IR2 = "));
    Serial.print(d.t_to_ir2_or_end_ms); Serial.println(F(" ms"));

    reason = waitEnter(F("[STEP 7A] Tekan ENTER untuk EJECT Grade A"));
    if (reason) { d.abort_reason = reason; return; }

    reason = pushStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR,
                                   PIN_LIMIT_SORTING, LOW, "SORTING");  // DIR LOW = maju ke limit
    if (reason) { d.abort_reason = reason; return; }
    reason = moveStepperSteps(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR,
                              STEPPER_RETRACT_SORT, HIGH, "SORTING");  // DIR HIGH = mundur
    if (reason) { d.abort_reason = reason; return; }
    Serial.println(F("[STEP 7A] OK. Grade A ter-eject."));
  } else { // grade == 'B'
    Serial.print(F("[STEP 7B] Konveyor jalan ")); Serial.print(END_OF_LINE_MS);
    Serial.println(F(" ms menuju end-of-line..."));
    reason = sleepAbortable(END_OF_LINE_MS);
    stopConveyor();
    d.t_to_ir2_or_end_ms = millis() - t_conveyor_restart;
    if (reason) { d.abort_reason = reason; return; }
    Serial.println(F("[STEP 7B] OK. Baterai jatuh di end-of-line. Durasi konveyor restart->end = "));
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

// Push stepper sampai limit switch tersentuh.
// Logika "edge": stop hanya saat transisi BEBAS(HIGH) -> TERSENTUH(LOW),
// supaya tidak instant-stop kalau carriage sudah menempel limit.
const char* pushStepperUntilLimit(int pulPin, int dirPin, int limitPin,
                                  int dir, const char* name) {
  Serial.print(F("  [STP ")); Serial.print(name); Serial.println(F("] dorong ke limit..."));
  digitalWrite(dirPin, dir);

  bool limitArmed = (digitalRead(limitPin) == HIGH);
  for (long i = 0; i < STEPPER_MAX_TO_LIMIT; i++) {
    if (digitalRead(PIN_EMERGENCY) == LOW) return "EMERGENCY_BUTTON";
    if (Serial.available()) {
      String s = readLineTrimmed();
      if (s.equalsIgnoreCase("ABORT")) return "ABORT_USER";
    }

    if (digitalRead(limitPin) == HIGH) {
      limitArmed = true;
    } else if (limitArmed) {
      return nullptr;  // limit tersentuh, sukses
    }

    digitalWrite(pulPin, HIGH); delayMicroseconds(STEPPER_PULSE_US);
    digitalWrite(pulPin, LOW);  delayMicroseconds(STEPPER_PULSE_US);
  }
  return "STEPPER_MAX_REACHED";  // 5000 step tanpa kena limit -> ada masalah
}

// Gerakkan stepper sejumlah step fixed. Abort-aware (limit TIDAK dicek
// karena ini biasanya gerakan mundur dari limit).
const char* moveStepperSteps(int pulPin, int dirPin, long steps, int dir,
                             const char* name) {
  Serial.print(F("  [STP ")); Serial.print(name); Serial.print(F("] gerak "));
  Serial.print(steps); Serial.println(F(" step..."));
  digitalWrite(dirPin, dir);

  for (long i = 0; i < steps; i++) {
    if (digitalRead(PIN_EMERGENCY) == LOW) return "EMERGENCY_BUTTON";
    // tidak baca Serial tiap step (terlalu sering) -- cukup tiap 64 step
    if ((i & 0x3F) == 0 && Serial.available()) {
      String s = readLineTrimmed();
      if (s.equalsIgnoreCase("ABORT")) return "ABORT_USER";
    }
    digitalWrite(pulPin, HIGH); delayMicroseconds(STEPPER_PULSE_US);
    digitalWrite(pulPin, LOW);  delayMicroseconds(STEPPER_PULSE_US);
  }
  return nullptr;
}

// ==========================================================================
//  HELPER: PENGUKURAN SoH  (sama dengan APPLY_SENSOR_AND_MEASURE di produksi)
// ==========================================================================
const char* measureSoH(CycleData& d) {
  if (!inaReady || !mlxReady || !dacReady) {
    Serial.println(F("  [WARN] Sensor I2C tidak lengkap -- pakai dummy bila perlu."));
  }

  d.temp_init_C = mlxReady ? mlx.readObjectTempC() : 0.0;

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
  Serial.println(F("  START   - mulai satu siklus workflow"));
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
  Serial.println(F(". Ketik START / STATUS / HELP."));
  Serial.print(F(" > "));
}

// Header CSV -- dicetak sekali saat boot
void printCSVHeader() {
  Serial.println();
  Serial.println(F(
    "CSV_HEADER,cycle_id,timestamp_ms,grade_manual,"
    "v_load_V,i_load_A,temp_init_C,temp_final_C,temp_delta_C,"
    "t_to_ir1_ms,t_push_ms,t_measure_ms,t_retract_ms,"
    "t_to_ir2_or_end_ms,abort_reason"));
}

void printCSVRow(const CycleData& d) {
  Serial.print(F("CSV,"));
  Serial.print(d.cycle_id);             Serial.print(',');
  Serial.print(d.timestamp_start_ms);   Serial.print(',');
  Serial.print(d.grade_manual);         Serial.print(',');
  Serial.print(d.v_load_V, 3);          Serial.print(',');
  Serial.print(d.i_load_A, 3);          Serial.print(',');
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
