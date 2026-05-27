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
    
    // Baca suhu baterai awal via sensor laser (MLX90614)
    float initialTemp = mlx.readObjectTempC();
    
    // 2. Pengukuran SoH via I2C Sensor
    digitalWrite(PIN_DAC_EN, HIGH); // Nyalakan Enable DAC
    dac.setVoltage(4095, false); // Berikan tegangan/beban maksimal via DAC I2C
    delay(2000); // Tahan beban untuk melihat Voltage Drop
    
    float v = 0.0, i = 0.0;
    if (i2cReady) {
      // Ambil 10 sampel untuk filter noise
      float sumV = 0, sumI = 0;
      for(int j=0; j<10; j++) {
        sumV += ina226.getBusVoltage_V();
        sumI += ina226.getCurrent_mA() / 1000.0;
        delay(10);
      }
      v = sumV / 10.0;
      i = sumI / 10.0;
    } else {
      // Dummy values jika modul I2C belum terpasang
      v = 3.75;
      i = 1.50;
    }
    
    float finalTemp = mlx.readObjectTempC();
    float tempDelta = finalTemp - initialTemp;
    
    dac.setVoltage(0, false); // Matikan Load DAC
    digitalWrite(PIN_DAC_EN, LOW); // Matikan Enable DAC
    
    // 3. Tarik Sensor mundur (asumsi butuh mundur 1000 step)
    moveStepper(PIN_STP_DRAIN_PUL, PIN_STP_DRAIN_DIR, PIN_STP_DRAIN_EN, 1000, LOW);
    
    sendTelemetryExt(v, i, tempDelta, "MEASUREMENT_DONE");
  }
  else if (cmd == "MOVE_TO_PROX_2") {
    startConveyorForward();
    currentState = STATE_WAIT_PROX_2;
  }
  else if (cmd == "EJECT_A") {
    moveStepperUntilLimit(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_STP_SORT_EN, PIN_LIMIT_SORTING, HIGH);
    moveStepper(PIN_STP_SORT_PUL, PIN_STP_SORT_DIR, PIN_STP_SORT_EN, 2500, LOW); // Mundur Ejector
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
void moveStepper(int pinStep, int pinDir, int pinEn, int steps, int dir) {
  digitalWrite(pinEn, LOW); // Enable Stepper Driver (Active Low biasanya)
  digitalWrite(pinDir, dir);
  for(int i=0; i<steps; i++) {
    digitalWrite(pinStep, HIGH);
    delayMicroseconds(400); 
    digitalWrite(pinStep, LOW);
    delayMicroseconds(400);
  }
  digitalWrite(pinEn, HIGH); // Disable Stepper
}

void moveStepperUntilLimit(int pinStep, int pinDir, int pinEn, int pinLimit, int dir) {
  digitalWrite(pinEn, LOW); 
  digitalWrite(pinDir, dir);
  
  // Maju maksimal 5000 step atau sampai limit switch tersentuh
  for(int i=0; i<5000; i++) {
    if (digitalRead(pinLimit) == LOW) break; // Asumsi Limit Switch Active Low
    
    digitalWrite(pinStep, HIGH);
    delayMicroseconds(400); 
    digitalWrite(pinStep, LOW);
    delayMicroseconds(400);
  }
  digitalWrite(pinEn, HIGH);
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
