/*
 * RECELL-AI Firmware (Arduino IDE / STM32duino)
 * Target: STM32F411CEU6 (BlackPill)
 * Optimization: 12-bit ADC enabled, Oversampling for High Precision
 */

#include <ArduinoJson.h>

// --- KONFIGURASI PIN ---
const int PIN_CONVEYOR_PWM = PA1; // PWM Speed (Set sangat lambat)
const int PIN_CONVEYOR_DIR = PA0;

const int PIN_PROX_1       = PB0; // Sensor Station
const int PIN_PROX_2       = PB1; // Grade A Eject Station

// Stepper 1: Pendorong Sensor Elektrik
const int PIN_STP_SENS_DIR = PB10;
const int PIN_STP_SENS_STP = PB11;
const int PIN_STP_SENS_EN  = PB12;

// Stepper 2: Pendorong Baterai Grade A
const int PIN_STP_EJCT_DIR = PA8;
const int PIN_STP_EJCT_STP = PA9;
const int PIN_STP_EJCT_EN  = PA10;

const int PIN_LOAD_PWM     = PA5;
const int PIN_VOLT_SENSE   = PA6;
const int PIN_CURR_SENSE   = PA7;

// --- STATE MACHINE ---
enum SystemState {
  STATE_IDLE,
  STATE_WAIT_PROX_1,
  STATE_WAIT_PROX_2,
  STATE_WAIT_END
};

SystemState currentState = STATE_IDLE;
int conveyorSpeed = 60; // 0-255, kecepatan lambat

void setup() {
  Serial.begin(115200); 
  
  // OPTIMASI STM32: Gunakan resolusi ADC 12-bit native STM32 (Nilai 0 - 4095)
  // Ini 4x lebih presisi daripada Arduino Uno biasa (10-bit).
  analogReadResolution(12);
  
  pinMode(PIN_CONVEYOR_DIR, OUTPUT);
  pinMode(PIN_CONVEYOR_PWM, OUTPUT);
  
  pinMode(PIN_PROX_1, INPUT_PULLUP);
  pinMode(PIN_PROX_2, INPUT_PULLUP);
  
  pinMode(PIN_STP_SENS_DIR, OUTPUT); pinMode(PIN_STP_SENS_STP, OUTPUT); pinMode(PIN_STP_SENS_EN, OUTPUT);
  pinMode(PIN_STP_EJCT_DIR, OUTPUT); pinMode(PIN_STP_EJCT_STP, OUTPUT); pinMode(PIN_STP_EJCT_EN, OUTPUT);
  digitalWrite(PIN_STP_SENS_EN, HIGH); 
  digitalWrite(PIN_STP_EJCT_EN, HIGH); 
  
  pinMode(PIN_LOAD_PWM, OUTPUT);
  pinMode(PIN_VOLT_SENSE, INPUT_ANALOG);
  pinMode(PIN_CURR_SENSE, INPUT_ANALOG);

  sendTelemetry(0, 0, "BOOT_OK");
}

void loop() {
  if (Serial.available() > 0) {
    String incomingStr = Serial.readStringUntil('\n');
    processCommand(incomingStr);
  }

  // --- NON-BLOCKING SENSOR CHECKS ---
  if (currentState == STATE_WAIT_PROX_1) {
    if (digitalRead(PIN_PROX_1) == LOW) {
      analogWrite(PIN_CONVEYOR_PWM, 0);
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "AT_PROX_1");
    }
  }
  
  if (currentState == STATE_WAIT_PROX_2) {
    if (digitalRead(PIN_PROX_2) == LOW) {
      analogWrite(PIN_CONVEYOR_PWM, 0);
      currentState = STATE_IDLE;
      sendTelemetry(0, 0, "AT_PROX_2");
    }
  }
}

// --- FUNGSI LOGIKA ---
void processCommand(String jsonStr) {
  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, jsonStr);
  if (error) return;

  String cmd = doc["cmd"];

  if (cmd == "MOVE_TO_PROX_1") {
    digitalWrite(PIN_CONVEYOR_DIR, HIGH);
    analogWrite(PIN_CONVEYOR_PWM, conveyorSpeed);
    currentState = STATE_WAIT_PROX_1;
  }
  else if (cmd == "APPLY_SENSOR_AND_MEASURE") {
    // 1. Dorong Sensor
    moveStepper(PIN_STP_SENS_STP, PIN_STP_SENS_DIR, PIN_STP_SENS_EN, 1000, HIGH); 
    
    // 2. Pengukuran SoH Presisi Tinggi (Oversampling)
    analogWrite(PIN_LOAD_PWM, 128); // Beban Constant Current ON
    delay(2000); // Tahan beban untuk melihat Voltage Drop
    
    // OVERSAMPLING: Ambil 50 sampel lalu rata-ratakan untuk membuang noise (Noise Filtering)
    long sumV = 0, sumI = 0;
    for(int i = 0; i < 50; i++) {
      sumV += analogRead(PIN_VOLT_SENSE);
      sumI += analogRead(PIN_CURR_SENSE);
      delay(2);
    }
    analogWrite(PIN_LOAD_PWM, 0); // Beban OFF
    
    float avgRawV = sumV / 50.0;
    float avgRawI = sumI / 50.0;
    
    // Konversi ADC 12-bit (4095) ke Voltage. Kalibrasi pengali (misal x2.0) sesuai Voltage Divider hardware
    float volt = (avgRawV / 4095.0) * 3.3 * 2.0; 
    float curr = (avgRawI / 4095.0) * 3.3; // Sesuaikan dengan nilai Shunt Resistor/Op-Amp
    
    // 3. Tarik Sensor mundur
    moveStepper(PIN_STP_SENS_STP, PIN_STP_SENS_DIR, PIN_STP_SENS_EN, 1000, LOW);
    
    sendTelemetry(volt, curr, "MEASUREMENT_DONE");
  }
  else if (cmd == "MOVE_TO_PROX_2") {
    digitalWrite(PIN_CONVEYOR_DIR, HIGH);
    analogWrite(PIN_CONVEYOR_PWM, conveyorSpeed);
    currentState = STATE_WAIT_PROX_2;
  }
  else if (cmd == "EJECT_A") {
    moveStepper(PIN_STP_EJCT_STP, PIN_STP_EJCT_DIR, PIN_STP_EJCT_EN, 2500, HIGH);
    moveStepper(PIN_STP_EJCT_STP, PIN_STP_EJCT_DIR, PIN_STP_EJCT_EN, 2500, LOW);
    sendTelemetry(0, 0, "EJECTED_A");
  }
  else if (cmd == "MOVE_TO_END") {
    digitalWrite(PIN_CONVEYOR_DIR, HIGH);
    analogWrite(PIN_CONVEYOR_PWM, conveyorSpeed);
    delay(5000);
    analogWrite(PIN_CONVEYOR_PWM, 0);
    sendTelemetry(0, 0, "DROPPED_B");
  }
}

void moveStepper(int pinStep, int pinDir, int pinEn, int steps, int dir) {
  digitalWrite(pinEn, LOW); // Enable Stepper Driver
  digitalWrite(pinDir, dir);
  for(int i=0; i<steps; i++) {
    digitalWrite(pinStep, HIGH);
    delayMicroseconds(400); // 400us sangat cepat namun tetap aman untuk torsi
    digitalWrite(pinStep, LOW);
    delayMicroseconds(400);
  }
  digitalWrite(pinEn, HIGH); // Disable Stepper Driver (Hemat listrik & kurangi panas)
}

void sendTelemetry(float v, float i, const char* status) {
  StaticJsonDocument<200> doc;
  // Membatasi angka di belakang koma untuk efisiensi serial
  doc["volt"] = serialized(String(v, 3)); 
  doc["curr"] = serialized(String(i, 3));
  doc["status"] = status;
  serializeJson(doc, Serial);
  Serial.println();
}
