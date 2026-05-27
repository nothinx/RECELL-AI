/*
 * ============================================================================
 *  RECELL-AI HARDWARE TEST SUITE  (v2)
 *  Target MCU : STM32F411CEU6  (STM32duino core)
 *  Serial     : 115200 baud, line ending "Newline" / "NL"
 * ----------------------------------------------------------------------------
 *  Alat uji aktuator & sensor satu per satu lewat MENU BERNOMOR.
 *  Ketik ANGKA pilihan lalu Enter. Tidak perlu menghafal sintaks perintah.
 *
 *  Keselamatan:
 *   - Selama aktuator bergerak, tekan ENTER kapan saja untuk MENGHENTIKAN.
 *   - Tombol EMERGENCY (PB5) menghentikan gerakan secara paksa.
 *   - Limit switch otomatis menghentikan stepper.
 *
 *  Catatan pinout (sesuai CSV "Konfirmasi Pinout Final"):
 *   - PA7 & PA6 adalah INPUT encoder (tidak dipakai untuk enable). Driver
 *     stepper diasumsikan SELALU AKTIF (pin ENABLE di-tie di hardware),
 *     sehingga MCU hanya mengirim PUL & DIR.
 * ============================================================================
 */

#include <Wire.h>
#include <INA226_WE.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MCP4725.h>

// --------------------------------------------------------------------------
//  KONFIGURASI PIN
// --------------------------------------------------------------------------
// Sensor digital (active-LOW, pakai pull-up internal)
const int PIN_LIMIT_DRAIN   = PB15;   // Limit switch drain station
const int PIN_LIMIT_SORTING = PA4;    // Limit switch sorting station
const int PIN_IR_DRAIN      = PB14;   // IR drain station
const int PIN_IR_SORTING    = PB12;   // IR sorting station
const int PIN_IR_BACKUP     = PB13;   // IR cadangan
const int PIN_EMERGENCY     = PB5;    // Tombol emergency / cut-off

// Encoder (INPUT) - cadangan untuk adjustment, bukan enable
const int PIN_ENC_DRAIN     = PA7;    // Encoder stepper drain
const int PIN_ENC_SORTING   = PA6;    // Encoder stepper sorting

// Konveyor BTS7960
const int PIN_CONVEYOR_EN   = PA5;    // Enable driver BTS7960
const int PIN_CONVEYOR_RPWM = PA1;    // R_PWM
const int PIN_CONVEYOR_LPWM = PA2;    // L_PWM

// Stepper (tanpa pin enable dari MCU)
const int PIN_STP_DRAIN_PUL = PB9;
const int PIN_STP_DRAIN_DIR = PB0;
const int PIN_STP_SORT_PUL  = PA8;
const int PIN_STP_SORT_DIR  = PA3;

// DAC gate (logika nyala/mati DAC supaya tidak noise)
const int PIN_DAC_GATE      = PB1;

// I2C
const int PIN_I2C_SDA       = PB7;
const int PIN_I2C_SCL       = PB6;

// Alamat I2C
const uint8_t ADDR_INA226   = 0x40;
const uint8_t ADDR_MLX90614 = 0x5A;
const uint8_t ADDR_MCP4725  = 0x62;

// Shunt INA226 -- WAJIB disesuaikan dengan board Anda, kalau salah arus salah.
const float INA_SHUNT_OHM   = 0.002;  // ohm
const float INA_MAX_AMP     = 10.0;   // ampere

// --------------------------------------------------------------------------
//  OBJEK SENSOR
// --------------------------------------------------------------------------
INA226_WE          ina226 = INA226_WE(ADDR_INA226);
Adafruit_MLX90614  mlx     = Adafruit_MLX90614();
Adafruit_MCP4725   dac;

bool inaReady = false;
bool mlxReady = false;
bool dacReady = false;

// ==========================================================================
//  SETUP
// ==========================================================================
void setup() {
  Serial.begin(115200);
  delay(800);

  // --- Pin sensor ---
  pinMode(PIN_LIMIT_DRAIN,   INPUT_PULLUP);
  pinMode(PIN_LIMIT_SORTING, INPUT_PULLUP);
  pinMode(PIN_IR_DRAIN,      INPUT_PULLUP);
  pinMode(PIN_IR_SORTING,    INPUT_PULLUP);
  pinMode(PIN_IR_BACKUP,     INPUT_PULLUP);
  pinMode(PIN_EMERGENCY,     INPUT_PULLUP);
  pinMode(PIN_ENC_DRAIN,     INPUT_PULLUP);
  pinMode(PIN_ENC_SORTING,   INPUT_PULLUP);

  // --- Pin konveyor (mulai mati) ---
  pinMode(PIN_CONVEYOR_EN,   OUTPUT);
  pinMode(PIN_CONVEYOR_RPWM, OUTPUT);
  pinMode(PIN_CONVEYOR_LPWM, OUTPUT);
  stopConveyor();

  // --- Pin stepper ---
  pinMode(PIN_STP_DRAIN_PUL, OUTPUT);
  pinMode(PIN_STP_DRAIN_DIR, OUTPUT);
  pinMode(PIN_STP_SORT_PUL,  OUTPUT);
  pinMode(PIN_STP_SORT_DIR,  OUTPUT);
  digitalWrite(PIN_STP_DRAIN_PUL, LOW);
  digitalWrite(PIN_STP_SORT_PUL,  LOW);

  // --- DAC gate (mulai mati) ---
  pinMode(PIN_DAC_GATE, OUTPUT);
  digitalWrite(PIN_DAC_GATE, LOW);

  // --- I2C & sensor ---
  Wire.setSDA(PIN_I2C_SDA);
  Wire.setSCL(PIN_I2C_SCL);
  Wire.begin();
  initSensors();

  printBanner();
  printMenu();
}

// ==========================================================================
//  LOOP UTAMA  (mesin menu)
// ==========================================================================
void loop() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) { printMenu(); return; }

  char choice = line.charAt(0);
  switch (choice) {
    case '1': scanI2C();        break;
    case '2': liveMonitor();    break;
    case '3': menuConveyor();   break;
    case '4': menuStepper(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR,
                          PIN_LIMIT_DRAIN, PIN_ENC_DRAIN, "DRAIN"); break;
    case '5': menuStepper(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR,
                          PIN_LIMIT_SORTING, PIN_ENC_SORTING, "SORTING"); break;
    case '6': menuDAC();        break;
    case '7': checkSensors();   break;
    case '0':
    case 'h':
    case 'H': break;            // hanya tampilkan menu lagi
    default:
      Serial.print(F("\n[!] Pilihan tidak dikenali: ")); Serial.println(line);
      break;
  }
  printMenu();
}

// ==========================================================================
//  TAMPILAN
// ==========================================================================
void printBanner() {
  Serial.println();
  Serial.println(F("============================================="));
  Serial.println(F("   RECELL-AI HARDWARE TEST SUITE  (v2)"));
  Serial.println(F("   MCU: STM32F411CEU6  |  Baud: 115200"));
  Serial.println(F("============================================="));
}

void printMenu() {
  Serial.println();
  Serial.println(F("---------------- MENU UTAMA -----------------"));
  Serial.println(F(" 1. Scan perangkat I2C"));
  Serial.println(F(" 2. Live monitor sensor   (ENTER = stop)"));
  Serial.println(F(" 3. Test konveyor BTS7960"));
  Serial.println(F(" 4. Test stepper DRAIN"));
  Serial.println(F(" 5. Test stepper SORTING"));
  Serial.println(F(" 6. Test DAC MCP4725"));
  Serial.println(F(" 7. Cek koneksi sensor (PASS/FAIL)"));
  Serial.println(F(" 0. Tampilkan menu ini lagi"));
  Serial.println(F("---------------------------------------------"));
  Serial.print(F("Pilihan > "));
}

// Cetak status sensor PASS/FAIL singkat
void printStatus(const __FlashStringHelper* label, bool ok) {
  Serial.print(ok ? F("[ OK ] ") : F("[FAIL] "));
  Serial.println(label);
}

// ==========================================================================
//  HELPER INPUT
// ==========================================================================
// Buang sisa karakter di buffer serial
void flushSerial() {
  while (Serial.available()) Serial.read();
}

// Baca satu baris (blocking). Kembalikan string sudah di-trim.
String readLineBlocking() {
  while (!Serial.available()) delay(5);
  String s = Serial.readStringUntil('\n');
  s.trim();
  return s;
}

// Minta angka ke user. Enter kosong = pakai nilai default.
long promptInt(const __FlashStringHelper* label, long defVal) {
  flushSerial();
  Serial.print(label);
  Serial.print(F(" [default ")); Serial.print(defVal); Serial.print(F("] > "));
  String s = readLineBlocking();
  if (s.length() == 0) { Serial.println(defVal); return defVal; }
  long v = s.toInt();
  Serial.println(v);
  return v;
}

// ==========================================================================
//  KESELAMATAN GERAKAN
// ==========================================================================
// Alasan abort umum (emergency / input user). Kembalikan nullptr bila aman.
// Limit switch TIDAK dicek di sini -- ditangani per-stepper dengan logika
// "edge" supaya tetap bisa mundur saat carriage sudah menempel limit.
const char* motionAbortReason() {
  if (digitalRead(PIN_EMERGENCY) == LOW) return "TOMBOL EMERGENCY DITEKAN";
  if (Serial.available()) { flushSerial(); return "DIBATALKAN OLEH USER (ENTER)"; }
  return nullptr;
}

// ==========================================================================
//  1. SCAN I2C
// ==========================================================================
void scanI2C() {
  Serial.println(F("\n[SCAN I2C] Memindai bus..."));
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print(F("  - Device di 0x"));
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      found++;
    }
  }
  if (found == 0) Serial.println(F("  Tidak ada device I2C ditemukan."));
  else { Serial.print(F("[SCAN I2C] Selesai, total ")); Serial.print(found); Serial.println(F(" device.")); }
}

// ==========================================================================
//  2. LIVE MONITOR SENSOR
// ==========================================================================
void liveMonitor() {
  flushSerial();
  Serial.println(F("\n[LIVE MONITOR] Refresh ~500ms. Tekan ENTER untuk berhenti."));
  delay(600);
  flushSerial();

  while (true) {
    printSensorBlock();
    // Tunggu ~500ms; berhenti lebih awal jika ada input.
    unsigned long t0 = millis();
    bool stop = false;
    while (millis() - t0 < 500) {
      if (Serial.available()) { stop = true; break; }
      delay(5);
    }
    if (stop) break;
  }
  flushSerial();
  Serial.println(F("\n[LIVE MONITOR] Dihentikan."));
}

// Cetak satu blok pembacaan semua sensor
void printSensorBlock() {
  Serial.println(F("\n.... PEMBACAAN SENSOR ........................"));
  printDigital(F("Emergency (PB5)  "), PIN_EMERGENCY, F("DITEKAN"), F("AMAN"));
  printDigital(F("Limit Drain (PB15)"), PIN_LIMIT_DRAIN, F("TERSENTUH"), F("BEBAS"));
  printDigital(F("Limit Sort  (PA4) "), PIN_LIMIT_SORTING, F("TERSENTUH"), F("BEBAS"));
  printDigital(F("IR Drain  (PB14)  "), PIN_IR_DRAIN, F("ADA OBJEK"), F("KOSONG"));
  printDigital(F("IR Sort   (PB12)  "), PIN_IR_SORTING, F("ADA OBJEK"), F("KOSONG"));
  printDigital(F("IR Backup (PB13)  "), PIN_IR_BACKUP, F("ADA OBJEK"), F("KOSONG"));
  Serial.print(F("Encoder Drain(PA7): ")); Serial.println(digitalRead(PIN_ENC_DRAIN));
  Serial.print(F("Encoder Sort (PA6): ")); Serial.println(digitalRead(PIN_ENC_SORTING));

  if (inaReady) {
    Serial.print(F("INA226 Tegangan   : ")); Serial.print(ina226.getBusVoltage_V(), 3); Serial.println(F(" V"));
    Serial.print(F("INA226 Arus       : ")); Serial.print(ina226.getCurrent_mA(), 1);   Serial.print(F(" mA  (shunt "));
    Serial.print(INA_SHUNT_OHM, 4); Serial.print(F(" ohm / ")); Serial.print(INA_MAX_AMP, 0); Serial.println(F(" A)"));
  } else {
    Serial.println(F("INA226            : TIDAK TERDETEKSI"));
  }
  if (mlxReady) {
    Serial.print(F("MLX90614 Objek    : ")); Serial.print(mlx.readObjectTempC(), 2);  Serial.println(F(" C"));
    Serial.print(F("MLX90614 Ambient  : ")); Serial.print(mlx.readAmbientTempC(), 2); Serial.println(F(" C"));
  } else {
    Serial.println(F("MLX90614          : TIDAK TERDETEKSI"));
  }
}

// Cetak baris sensor digital active-LOW dengan label kondisi
void printDigital(const __FlashStringHelper* label, int pin,
                  const __FlashStringHelper* lowTxt, const __FlashStringHelper* highTxt) {
  Serial.print(label); Serial.print(F(": "));
  Serial.println(digitalRead(pin) == LOW ? lowTxt : highTxt);
}

// ==========================================================================
//  3. TEST KONVEYOR
// ==========================================================================
void menuConveyor() {
  long speed = promptInt(F("Kecepatan konveyor (-255..255, + maju / - mundur)"), 150);
  speed = constrain(speed, -255, 255);
  if (speed == 0) { Serial.println(F("[KONVEYOR] Kecepatan 0 -> konveyor mati.")); stopConveyor(); return; }

  digitalWrite(PIN_CONVEYOR_EN, HIGH);
  if (speed > 0) { analogWrite(PIN_CONVEYOR_LPWM, 0); analogWrite(PIN_CONVEYOR_RPWM, speed); }
  else           { analogWrite(PIN_CONVEYOR_RPWM, 0); analogWrite(PIN_CONVEYOR_LPWM, -speed); }

  Serial.print(F("[KONVEYOR] Berjalan, kecepatan = ")); Serial.print(speed);
  Serial.println(F(". Tekan ENTER atau EMERGENCY untuk stop."));

  flushSerial();
  const char* reason = nullptr;
  while ((reason = motionAbortReason()) == nullptr) delay(10);

  stopConveyor();
  Serial.print(F("[KONVEYOR] Berhenti -> ")); Serial.println(reason);
}

void stopConveyor() {
  analogWrite(PIN_CONVEYOR_RPWM, 0);
  analogWrite(PIN_CONVEYOR_LPWM, 0);
  digitalWrite(PIN_CONVEYOR_EN, LOW);
}

// ==========================================================================
//  4 & 5. TEST STEPPER
// ==========================================================================
void menuStepper(int pulPin, int dirPin, int limitPin, int encPin, const char* name) {
  Serial.print(F("\n[STEPPER ")); Serial.print(name); Serial.println(F("]"));
  long steps = promptInt(F("Jumlah langkah (+/- untuk arah)"), 800);
  long del   = promptInt(F("Delay per setengah-pulsa (us)"), 600);
  if (del <= 0) del = 600;

  bool reverse = (steps < 0);
  long total   = labs(steps);
  digitalWrite(dirPin, reverse ? LOW : HIGH);

  Serial.print(F("Bergerak ")); Serial.print(total);
  Serial.print(F(" langkah, arah=")); Serial.print(reverse ? F("MUNDUR") : F("MAJU"));
  Serial.print(F(", delay=")); Serial.print(del); Serial.println(F(" us"));
  Serial.println(F("(Tekan ENTER / EMERGENCY untuk stop)"));

  // Logika limit "edge": kalau carriage sudah menempel limit saat start,
  // gerakan TIDAK langsung diblok (supaya bisa mundur). Limit baru
  // menghentikan bila tersentuh dari kondisi bebas (transisi BEBAS->TERSENTUH).
  bool limitArmed = (digitalRead(limitPin) == HIGH);
  if (!limitArmed)
    Serial.println(F("(Info: limit sedang tertekan -> gerakan dipakai untuk mundur)"));

  flushSerial();
  long done = 0;
  long encEdges = 0;
  int  lastEnc = digitalRead(encPin);
  const char* reason = nullptr;

  for (long i = 0; i < total; i++) {
    reason = motionAbortReason();
    if (reason) break;

    // Re-arm setelah limit terlepas; stop hanya saat tersentuh dlm keadaan armed.
    if (digitalRead(limitPin) == HIGH) {
      limitArmed = true;
    } else if (limitArmed) {
      reason = "LIMIT SWITCH TERSENTUH";
      break;
    }

    digitalWrite(pulPin, HIGH); delayMicroseconds(del);
    digitalWrite(pulPin, LOW);  delayMicroseconds(del);
    done++;

    int e = digitalRead(encPin);              // hitung transisi encoder (referensi adjustment)
    if (e != lastEnc) { encEdges++; lastEnc = e; }
  }

  Serial.print(F("Selesai. Langkah dieksekusi: ")); Serial.print(done);
  Serial.print(F(" / ")); Serial.println(total);
  Serial.print(F("Transisi encoder (sampling per-langkah, kasar): ")); Serial.println(encEdges);
  if (reason) { Serial.print(F("Berhenti lebih awal -> ")); Serial.println(reason); }
}

// ==========================================================================
//  6. TEST DAC
// ==========================================================================
void menuDAC() {
  if (!dacReady) { Serial.println(F("\n[DAC] MCP4725 tidak terdeteksi. Cek koneksi/alamat.")); return; }
  long val = promptInt(F("Nilai DAC (0-4095)"), 2048);
  val = constrain(val, 0, 4095);

  digitalWrite(PIN_DAC_GATE, HIGH);   // nyalakan logika DAC
  dac.setVoltage((uint16_t)val, false);
  Serial.print(F("[DAC] Output diset ke ")); Serial.print(val); Serial.println(F(" / 4095"));
  Serial.println(F("(Gate DAC = ON. Pilih lagi menu 6 dengan nilai berbeda untuk ubah.)"));
}

// ==========================================================================
//  7. CEK KONEKSI SENSOR
// ==========================================================================
void checkSensors() {
  Serial.println(F("\n---------- CEK KONEKSI SENSOR I2C ----------"));
  initSensors();
  printStatus(F("INA226   (0x40)"), inaReady);
  printStatus(F("MLX90614 (0x5A)"), mlxReady);
  printStatus(F("MCP4725  (0x62)"), dacReady);
  Serial.println(F("--------------------------------------------"));
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
}
