/*
 * ============================================================================
 *  RECELL-AI STEPPER TEST  (v1)
 *  Target MCU : STM32F411CEU6  (STM32duino core)
 *  Serial     : 115200 baud, line ending "Newline" / "NL"
 * ----------------------------------------------------------------------------
 *  Program FOKUS untuk mengonfirmasi:
 *    1. Pasangan pin (PUL, DIR) mana yang nyatanya menggerakkan motor mana
 *       (drain vs sorting -- sering tertukar saat wiring).
 *    2. DIR=LOW = MAJU (ke arah limit switch), DIR=HIGH = MUNDUR
 *       (atau sebaliknya -- tinggal observasi).
 *
 *  Label pin sengaja netral ("Stepper A" / "Stepper B") supaya user observasi
 *  motor fisik mana yang bergerak -- TIDAK menganggap nama "drain"/"sort"
 *  sudah benar di hardware.
 *
 *    Stepper A : PUL=PB9 (sesuai CSV "PUL DRAIN")
 *                DIR=PB0 (sesuai CSV "DIR DRAIN")
 *    Stepper B : PUL=PA8 (sesuai CSV "PUL SORT")
 *                DIR=PA3 (sesuai CSV "DIR SORT")
 *
 *  Limit switch (active LOW):
 *    LIMIT 1 : PB15 (sesuai CSV "LIMIT DRAIN")
 *    LIMIT 2 : PA4  (sesuai CSV "LIMIT SORT")
 *
 *  Pakai program ini DULU sebelum WORKFLOW_TEST untuk:
 *    - Konfirmasi PUL/DIR tidak terbalik
 *    - Konfirmasi mapping A/B vs motor drain/sort fisik
 *    - Konfirmasi arah LOW/HIGH = maju/mundur
 *  Hasil test dipakai untuk seting akhir di WORKFLOW_TEST.ino.
 * ============================================================================
 */

// --------------------------------------------------------------------------
//  PINOUT (sesuai CSV "Konfirmasi Pinout Final")
// --------------------------------------------------------------------------
const int PIN_A_PUL = PB9;   // Stepper A pulse
const int PIN_A_DIR = PB0;   // Stepper A direction
const int PIN_B_PUL = PA8;   // Stepper B pulse
const int PIN_B_DIR = PA3;   // Stepper B direction

const int PIN_LIMIT_1 = PB15;  // Limit DRAIN (label CSV)
const int PIN_LIMIT_2 = PA4;   // Limit SORT  (label CSV)

const int PIN_IR_DRAIN   = PB14;
const int PIN_IR_SORTING = PB12;
const int PIN_IR_BACKUP  = PB13;
const int PIN_EMERGENCY  = PB5;

// --------------------------------------------------------------------------
//  PARAMETER
// --------------------------------------------------------------------------
const long  DEFAULT_STEPS      = 200;
const long  PULSE_US           = 400;       // setengah-pulsa (matched RECELL_STM32)
const long  STEPS_MAX_TO_LIMIT = 5000;      // batas aman

// ==========================================================================
//  SETUP
// ==========================================================================
void setup() {
  Serial.begin(115200);
  delay(800);

  pinMode(PIN_A_PUL, OUTPUT);  digitalWrite(PIN_A_PUL, LOW);
  pinMode(PIN_A_DIR, OUTPUT);  digitalWrite(PIN_A_DIR, LOW);
  pinMode(PIN_B_PUL, OUTPUT);  digitalWrite(PIN_B_PUL, LOW);
  pinMode(PIN_B_DIR, OUTPUT);  digitalWrite(PIN_B_DIR, LOW);

  pinMode(PIN_LIMIT_1, INPUT_PULLUP);
  pinMode(PIN_LIMIT_2, INPUT_PULLUP);
  pinMode(PIN_IR_DRAIN,   INPUT_PULLUP);
  pinMode(PIN_IR_SORTING, INPUT_PULLUP);
  pinMode(PIN_IR_BACKUP,  INPUT_PULLUP);
  pinMode(PIN_EMERGENCY,  INPUT_PULLUP);

  printBanner();
  printMenu();
}

// ==========================================================================
//  LOOP
// ==========================================================================
void loop() {
  if (!Serial.available()) return;

  String s = Serial.readStringUntil('\n');
  s.trim();
  if (s.length() == 0) { printMenu(); return; }

  char c = s.charAt(0);
  switch (c) {
    case '1': moveSteps(PIN_A_PUL, PIN_A_DIR, DEFAULT_STEPS, LOW,  "A", "LOW");  break;
    case '2': moveSteps(PIN_A_PUL, PIN_A_DIR, DEFAULT_STEPS, HIGH, "A", "HIGH"); break;
    case '3': moveSteps(PIN_B_PUL, PIN_B_DIR, DEFAULT_STEPS, LOW,  "B", "LOW");  break;
    case '4': moveSteps(PIN_B_PUL, PIN_B_DIR, DEFAULT_STEPS, HIGH, "B", "HIGH"); break;

    case '5': moveToLimit(PIN_A_PUL, PIN_A_DIR, PIN_LIMIT_1, LOW,  "A", "LIMIT_1", "LOW");  break;
    case '6': moveToLimit(PIN_A_PUL, PIN_A_DIR, PIN_LIMIT_1, HIGH, "A", "LIMIT_1", "HIGH"); break;
    case '7': moveToLimit(PIN_B_PUL, PIN_B_DIR, PIN_LIMIT_2, LOW,  "B", "LIMIT_2", "LOW");  break;
    case '8': moveToLimit(PIN_B_PUL, PIN_B_DIR, PIN_LIMIT_2, HIGH, "B", "LIMIT_2", "HIGH"); break;

    case 'c': case 'C': moveCustom(); break;
    case 's': case 'S': printStatus(); break;
    case 'h': case 'H': case '?': case '0': break;
    default:
      Serial.print(F("[!] Pilihan tidak dikenali: ")); Serial.println(s);
      break;
  }
  printMenu();
}

// ==========================================================================
//  AKSI GERAK
// ==========================================================================
void moveSteps(int pulPin, int dirPin, long steps, int dir,
               const char* name, const char* dirLabel) {
  Serial.println();
  Serial.print(F("[STEPPER ")); Serial.print(name);
  Serial.print(F("] DIR=")); Serial.print(dirLabel);
  Serial.print(F(", steps=")); Serial.println(steps);
  Serial.println(F("(ENTER atau EMERGENCY untuk stop)"));

  digitalWrite(dirPin, dir);
  delayMicroseconds(20);  // settle direction

  flushSerial();
  const char* reason = nullptr;
  long done = 0;
  for (long i = 0; i < steps; i++) {
    reason = abortReason();
    if (reason) break;

    digitalWrite(pulPin, HIGH); delayMicroseconds(PULSE_US);
    digitalWrite(pulPin, LOW);  delayMicroseconds(PULSE_US);
    done++;
  }
  Serial.print(F("  Langkah dieksekusi: ")); Serial.print(done);
  Serial.print(F(" / ")); Serial.println(steps);
  if (reason) { Serial.print(F("  Dihentikan: ")); Serial.println(reason); }
}

void moveToLimit(int pulPin, int dirPin, int limitPin, int dir,
                 const char* name, const char* limitLabel, const char* dirLabel) {
  Serial.println();
  Serial.print(F("[STEPPER ")); Serial.print(name);
  Serial.print(F("] DIR=")); Serial.print(dirLabel);
  Serial.print(F(" -> ")); Serial.print(limitLabel);
  Serial.print(F(" (max ")); Serial.print(STEPS_MAX_TO_LIMIT); Serial.println(F(" step)"));
  Serial.println(F("(ENTER atau EMERGENCY untuk stop)"));

  digitalWrite(dirPin, dir);
  delayMicroseconds(20);

  // Logika edge: kalau limit sudah tertekan saat start, gerakan tetap berjalan
  // sampai limit RELEASE-PRESS lagi (supaya bisa mundur dari limit).
  bool limitArmed = (digitalRead(limitPin) == HIGH);
  if (!limitArmed)
    Serial.println(F("  (Info: limit sudah tertekan -> gerakan dipakai untuk mundur)"));

  flushSerial();
  const char* reason = nullptr;
  long done = 0;
  for (long i = 0; i < STEPS_MAX_TO_LIMIT; i++) {
    reason = abortReason();
    if (reason) break;

    if (digitalRead(limitPin) == HIGH) {
      limitArmed = true;
    } else if (limitArmed) {
      reason = "LIMIT TERSENTUH";
      break;
    }

    digitalWrite(pulPin, HIGH); delayMicroseconds(PULSE_US);
    digitalWrite(pulPin, LOW);  delayMicroseconds(PULSE_US);
    done++;
  }
  Serial.print(F("  Langkah dieksekusi: ")); Serial.print(done);
  Serial.print(F(" / ")); Serial.println(STEPS_MAX_TO_LIMIT);
  if (reason) { Serial.print(F("  ")); Serial.println(reason); }
  else        { Serial.println(F("  [!] Maksimum tercapai TANPA kena limit -- cek wiring/limit polarity.")); }
}

// Custom: user pilih stepper, dir, dan jumlah step
void moveCustom() {
  Serial.println();
  Serial.println(F("Stepper? (a=A / b=B): "));
  String s1 = readBlocking();
  Serial.println(F("Direction? (l=LOW / h=HIGH): "));
  String s2 = readBlocking();
  Serial.println(F("Jumlah step (default 100): "));
  String s3 = readBlocking();

  int pulPin, dirPin;
  const char* name;
  if (s1.length() && (s1.charAt(0) == 'a' || s1.charAt(0) == 'A')) {
    pulPin = PIN_A_PUL; dirPin = PIN_A_DIR; name = "A";
  } else {
    pulPin = PIN_B_PUL; dirPin = PIN_B_DIR; name = "B";
  }
  int dir; const char* dirLabel;
  if (s2.length() && (s2.charAt(0) == 'l' || s2.charAt(0) == 'L')) {
    dir = LOW;  dirLabel = "LOW";
  } else {
    dir = HIGH; dirLabel = "HIGH";
  }
  long steps = s3.length() ? s3.toInt() : 100;
  if (steps <= 0) steps = 100;

  moveSteps(pulPin, dirPin, steps, dir, name, dirLabel);
}

// ==========================================================================
//  HELPER
// ==========================================================================
String readBlocking() {
  while (!Serial.available()) delay(5);
  String s = Serial.readStringUntil('\n');
  s.trim();
  return s;
}

void flushSerial() { while (Serial.available()) Serial.read(); }

const char* abortReason() {
  if (digitalRead(PIN_EMERGENCY) == LOW) return "EMERGENCY DITEKAN";
  if (Serial.available()) { flushSerial(); return "DIBATALKAN (ENTER)"; }
  return nullptr;
}

void printBanner() {
  Serial.println();
  Serial.println(F("============================================="));
  Serial.println(F("   RECELL-AI STEPPER TEST  (v1)"));
  Serial.println(F("   Stepper A: PUL=PB9 DIR=PB0  (CSV: drain)"));
  Serial.println(F("   Stepper B: PUL=PA8 DIR=PA3  (CSV: sort) "));
  Serial.println(F("   Limit 1 : PB15 (CSV: drain) "));
  Serial.println(F("   Limit 2 : PA4  (CSV: sort)  "));
  Serial.println(F("============================================="));
}

void printMenu() {
  Serial.println();
  Serial.println(F("------------------ MENU ---------------------"));
  Serial.println(F(" 1. Stepper A , DIR=LOW , 200 step"));
  Serial.println(F(" 2. Stepper A , DIR=HIGH, 200 step"));
  Serial.println(F(" 3. Stepper B , DIR=LOW , 200 step"));
  Serial.println(F(" 4. Stepper B , DIR=HIGH, 200 step"));
  Serial.println(F(" 5. Stepper A -> LIMIT 1 (PB15), DIR=LOW"));
  Serial.println(F(" 6. Stepper A -> LIMIT 1 (PB15), DIR=HIGH"));
  Serial.println(F(" 7. Stepper B -> LIMIT 2 (PA4),  DIR=LOW"));
  Serial.println(F(" 8. Stepper B -> LIMIT 2 (PA4),  DIR=HIGH"));
  Serial.println(F(" c. Custom (pilih stepper / dir / step)"));
  Serial.println(F(" s. Status sensor (limit, IR, emergency)"));
  Serial.println(F(" h. Tampilkan menu ini lagi"));
  Serial.println(F("---------------------------------------------"));
  Serial.print(F("Pilihan > "));
}

void printStatus() {
  Serial.println();
  Serial.println(F(".... STATUS SENSOR ........................."));
  printDigital(F("Emergency (PB5)   "), PIN_EMERGENCY,  F("DITEKAN"),  F("AMAN"));
  printDigital(F("Limit 1   (PB15)  "), PIN_LIMIT_1,    F("TERSENTUH"),F("BEBAS"));
  printDigital(F("Limit 2   (PA4)   "), PIN_LIMIT_2,    F("TERSENTUH"),F("BEBAS"));
  printDigital(F("IR Drain  (PB14)  "), PIN_IR_DRAIN,   F("ADA OBJEK"),F("KOSONG"));
  printDigital(F("IR Sort   (PB12)  "), PIN_IR_SORTING, F("ADA OBJEK"),F("KOSONG"));
  printDigital(F("IR Backup (PB13)  "), PIN_IR_BACKUP,  F("ADA OBJEK"),F("KOSONG"));
}

void printDigital(const __FlashStringHelper* label, int pin,
                  const __FlashStringHelper* lowTxt, const __FlashStringHelper* highTxt) {
  Serial.print(label); Serial.print(F(": "));
  Serial.println(digitalRead(pin) == LOW ? lowTxt : highTxt);
}
