# Implementation Plan: RECELL-AI Battery Classification

**Project:** RECELL-AI
**AI Model:** YOLOv8n (Nano)
**Platform:** Jetson Orin Nano + STM32F411
**Timeline Goal:** KIWIE Korea 2026

---

## Phase 1: Environment & AI Setup (Jetson)
*Goal: Get YOLOv8n running at maximum performance on Orin Nano.*

1.  **System Preparation:**
    *   Install JetPack 6.x (Ubuntu 22.04).
    *   Install Python 3.10, PyTorch (Jetson version), and Ultralytics.
2.  **Model Optimization:**
    *   Train YOLOv8n on the custom battery dataset (Normal, Rust, Dent).
    *   **Export to TensorRT (`.engine`):** This is critical for 30+ FPS inference on the Orin Nano.
3.  **Vision Pipeline:**
    *   Implement an asynchronous camera thread (OpenCV/GStreamer).
    *   Create a detection wrapper that returns a "Physical Health Score".

---

## Phase 2: Firmware Development (STM32)
*Goal: Reliable sensor reading and motor execution.*

1.  **Peripherals Initialization:**
    *   **ADC + DMA:** For high-speed, low-jitter voltage and current sampling.
    *   **PWM/Timers:** For Stepper motor control and Electronic Load management.
    *   **UART (USB-CDC):** For communication with Jetson.
2.  **Core Logic:**
    *   Implement **Constant Current Load** control loop (PID or simple threshold).
    *   Calculate SoH based on discharge curve parameters.
3.  **Command Execution:**
    *   Implement a parser for commands like `START_TEST`, `MOVE_CONVEYOR`, `SORT_A/B/C`.

---

## Phase 3: Communication & Protocol
*Goal: Fast and fail-safe data exchange.*

1.  **Protocol Definition:** Use a structured packet format (JSON-like or COBS-encoded binary).
2.  **Handshake:** Ensure Jetson and STM32 verify connection on startup.
3.  **Error Handling:** Define behavior if serial disconnects or a battery gets stuck.

---

## Phase 4: Integration & Mechanical Testing
*Goal: Full system automation.*

1.  **Sequence Logic:**
    *   `Step 1`: Conveyor moves battery to Vision Station.
    *   `Step 2`: Jetson triggers YOLOv8n -> Physical Check.
    *   `Step 3`: Conveyor moves battery to Electrical Station.
    *   `Step 4`: STM32 runs SoH test -> Sends data to Jetson.
    *   `Step 5`: Jetson decides Final Grade -> STM32 sorts via Stepper.
2.  **Fine-tuning:** Adjust motor speeds and sensor calibration.

---

## Phase 5: Documentation & Final Polish
*Goal: KIWIE Competition Readiness.*

1.  **Data Logging:** Jetson logs every test result to a CSV/Database for the "Judging Report".
2.  **UI/Dashboard:** (Optional) Simple GUI on Jetson to show real-time grading status.
3.  **Final Documentation:** Update HKI and Technical Specs with real-world test data.
