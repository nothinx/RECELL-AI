# Software Architecture Design: RECELL-AI

**Project:** RECELL-AI Battery Classification
**Master:** Jetson Orin Nano (AI, Logic, UI)
**Slave:** STM32F411 (Sensors, Actuators, Motion)
**Communication:** USB-Serial (115200 bps recommended)

---

## 1. High-Level System Flow
1. **Trigger:** Battery enters the conveyor/station (detected by sensor).
2. **Vision Phase (Jetson):** Capture image -> Run AI Inference -> Detect Physical Anomaly.
3. **Electrical Phase (STM32):** Load applied -> Measure V/I -> Calculate SoH.
4. **Decision (Jetson):** Combine Physical + Electrical data -> Determine Grade (A/B/Recycle).
5. **Action (STM32):** Jetson sends command -> STM32 activates Stepper Sorting Mechanism.

---

## 2. Jetson Orin Nano Architecture (Master)
The Jetson software will be Python-based for flexibility with AI libraries.

### Modules:
*   **Vision Engine:** OpenCV + TensorRT (Inference). Processes camera stream.
*   **Communication Manager:** Handles Serial I/O (PySerial). Manages command queue to STM32.
*   **Decision Logic:** Aggregates AI results and STM32 sensor data to finalize the grade.
*   **Main Coordinator:** Asynchronous loop managing state transitions.

---

## 3. STM32F411 Architecture (Slave)
The STM32 firmware will be C-based (HAL/LL) focusing on deterministic timing.

### Key Tasks:
*   **State Machine:**
    *   `IDLE`: Waiting for commands.
    *   `MEASURING`: Controlling Constant Current Load and reading ADC.
    *   `SORTING`: Executing stepper motor sequences.
*   **Interrupts:**
    *   `UART_RX_IRQ`: For fast command receiving from Jetson.
    *   `TIMER_IRQ`: For precise PWM (Stepper) and ADC sampling frequency.

---

## 4. Communication Protocol (Serial JSON or Binary)
*Example Command Format (Jetson to STM32):*
`{"cmd": "SORT", "grade": "A"}`

*Example Feedback Format (STM32 to Jetson):*
`{"status": "READY", "volt": 3.75, "curr": 1.0}`

---

## 5. Directory Structure for Implementation
```
RECELL-AI/
├── firmware/
│   ├── Core/
│   │   ├── src/ (Main, State Machine, ISRs)
│   │   └── inc/ (Protocol definitions)
│   └── Drivers/
├── jetson/
│   ├── models/ (TensorRT engines)
│   ├── src/
│   │   ├── vision/ (Camera & AI inference)
│   │   ├── serial_comm/ (Communication wrapper)
│   │   └── core/ (Main logic & state)
│   └── requirements.txt
└── ...
```
