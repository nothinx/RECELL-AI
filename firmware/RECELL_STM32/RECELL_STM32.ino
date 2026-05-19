/*
 * RECELL-AI Firmware (Arduino IDE / STM32duino)
 * Target: STM32F411
 */

#include <ArduinoJson.h> // Membutuhkan library ArduinoJson dari Library Manager

// --- KONFIGURASI PIN (Sesuaikan nanti) ---
const int PIN_CONVEYOR_PWM = PA1;
const int PIN_CONVEYOR_DIR = PA0;

const int PIN_STEPPER_DIR  = PB10;
const int PIN_STEPPER_STEP = PB11;
const int PIN_STEPPER_EN   = PB12;

const int PIN_LOAD_PWM     = PA5;
const int PIN_VOLT_SENSE   = PA6;
const int PIN_CURR_SENSE   = PA7;

// --- STATE MACHINE ---
enum SystemState {
  STATE_IDLE,
  STATE_SOH_MEASURING,
  STATE_SORTING
};

SystemState currentState = STATE_IDLE;

void setup() {
  Serial.begin(115200); // Komunikasi dengan Jetson
  
  // Inisialisasi Pin
  pinMode(PIN_CONVEYOR_DIR, OUTPUT);
  pinMode(PIN_CONVEYOR_PWM, OUTPUT);
  
  pinMode(PIN_STEPPER_DIR, OUTPUT);
  pinMode(PIN_STEPPER_STEP, OUTPUT);
  pinMode(PIN_STEPPER_EN, OUTPUT);
  digitalWrite(PIN_STEPPER_EN, HIGH); // Disable stepper awal
  
  pinMode(PIN_LOAD_PWM, OUTPUT);
  pinMode(PIN_VOLT_SENSE, INPUT_ANALOG);
  pinMode(PIN_CURR_SENSE, INPUT_ANALOG);

  sendTelemetry(0, 0, "BOOT_OK");
}

void loop() {
  // Cek apakah ada pesan masuk dari Jetson
  if (Serial.available() > 0) {
    String incomingStr = Serial.readStringUntil('\n');
    processCommand(incomingStr);
  }

  // Jika sedang mode SOH, jalankan fungsi non-blocking atau state machine
  if (currentState == STATE_SOH_MEASURING) {
    measureSOH();
  }
}

// --- FUNGSI LOGIKA ---

void processCommand(String jsonStr) {
  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, jsonStr);

  if (error) {
    return; // Abaikan pesan gagal parse
  }

  String cmd = doc["cmd"];

  if (cmd == "TEST_CONVEYOR") {
    digitalWrite(PIN_CONVEYOR_DIR, HIGH);
    analogWrite(PIN_CONVEYOR_PWM, 100); // PWM 0-255
    sendTelemetry(0, 0, "TESTING_CONVEYOR");
  } 
  else if (cmd == "STOP_CONVEYOR") {
    analogWrite(PIN_CONVEYOR_PWM, 0);
    sendTelemetry(0, 0, "IDLE");
  }
  else if (cmd == "TEST_STEPPER") {
    moveStepper(100, HIGH);
    sendTelemetry(0, 0, "STEPPER_DONE");
  }
  else if (cmd == "START_SOH") {
    currentState = STATE_SOH_MEASURING;
  }
  else if (cmd == "SORT") {
    String grade = doc["grade"];
    if (grade == "A") executeSort('A');
    else if (grade == "B") executeSort('B');
    else if (grade == "R") executeSort('R');
  }
}

void measureSOH() {
  // Simulasi nyalakan beban
  analogWrite(PIN_LOAD_PWM, 128); 
  delay(10); // Waktu stabilisasi (Gunakan millis() untuk non-blocking di versi final)
  
  int rawV = analogRead(PIN_VOLT_SENSE);
  int rawI = analogRead(PIN_CURR_SENSE);
  
  // Konversi kasar ke float (Sesuaikan pengali dengan rangkaian)
  float volt = (rawV / 1023.0) * 3.3 * 2.0; 
  float curr = (rawI / 1023.0) * 3.3;

  analogWrite(PIN_LOAD_PWM, 0); // Matikan beban
  
  sendTelemetry(volt, curr, "MEASURING_DONE");
  currentState = STATE_IDLE;
}

void executeSort(char grade) {
  currentState = STATE_SORTING;
  
  if (grade == 'A') {
    moveStepper(200, HIGH); // Maju 200 step
  } else if (grade == 'R') {
    moveStepper(200, LOW);  // Mundur 200 step
  }

  sendTelemetry(0, 0, "SORT_DONE");
  currentState = STATE_IDLE;
}

void moveStepper(int steps, int dir) {
  digitalWrite(PIN_STEPPER_EN, LOW); // Enable
  digitalWrite(PIN_STEPPER_DIR, dir);
  
  for(int i=0; i<steps; i++) {
    digitalWrite(PIN_STEPPER_STEP, HIGH);
    delayMicroseconds(500); // Kecepatan motor
    digitalWrite(PIN_STEPPER_STEP, LOW);
    delayMicroseconds(500);
  }
  
  digitalWrite(PIN_STEPPER_EN, HIGH); // Disable untuk hemat arus
}

void sendTelemetry(float v, float i, const char* status) {
  // Kirim data format JSON kembali ke Jetson
  StaticJsonDocument<200> doc;
  doc["volt"] = v;
  doc["curr"] = i;
  doc["status"] = status;
  
  serializeJson(doc, Serial);
  Serial.println(); // Terminator
}
