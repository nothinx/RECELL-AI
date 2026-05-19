# Technical Specification & Documentation: RECELL-AI

**Project:** RECELL-AI (Fully Automated Second-Life Battery Grading Machine)
**Competition:** KIWIE Korea 2026
**Date:** 2026-05-19

## 1. System Overview
RECELL-AI is an automated system designed to grade 18650 Li-ion batteries by combining electrical analysis and computer vision. It bridges the gap in the circular economy by providing a decentralized and reliable solution for e-waste management.

## 2. Technical Architecture
The system follows a dual-controller architecture:
*   **Microcontroller (STM32F411):** 
    *   Sensor acquisition (Current, Voltage).
    *   Motion control (Conveyor, Stepper-motor sorting mechanism).
    *   Implementation of the **Constant Current Load** method for discharging tests.
*   **Edge AI Processor (NVIDIA Jetson Orin Nano):**
    *   Visual inspection using Computer Vision.
    *   Anomaly detection (Rust, Dents, Physical damage).
    *   Integration of AI-driven classification.

## 3. Grading Methodology
### 3.1. Electrical Grading (State of Health - SoH)
*   **Method:** Constant Current Load.
*   **Process:** Measuring discharge parameters to determine the real capacity and health of the battery.
*   **Output:** Numerical health score (SoH).

### 3.2. Visual Grading (Physical Integrity)
*   **Method:** Edge AI-powered Computer Vision.
*   **Detection Targets:** 
    *   Rust/Corrosion.
    *   Physical Dents/Deformation.
    *   Label/Safety issues.

### 3.3. Final Classification
Batteries are categorized into:
*   **Grade A/B:** Suitable for second-life applications (Power banks, UPS, etc.).
*   **End-of-Life (Recycle):** Severely degraded cells recommended for chemical recycling.

## 4. Hardware Components (Initial List)
| Component | Function |
| :--- | :--- |
| STM32F411 | Main controller for electronics and motion. |
| NVIDIA Jetson Orin Nano | High-level AI and Computer Vision. |
| Constant Current Load Circuit | For accurate battery discharging. |
| Voltage/Current Sensors | Monitoring electrical parameters. |
| Stepper Motors | Sorting mechanism. |
| Conveyor System | Battery transport. |
| Camera Module | Image acquisition for AI. |

## 5. Software Requirements
*   **Firmware:** C/C++ (STM32 HAL/LL or CMSIS).
*   **AI/Inference:** Python, TensorRT (for optimized inference on Jetson).
*   **Vision:** OpenCV, Deep Learning Model (CNN/YOLO variant).
*   **Communication:** UART/I2C between STM32 and Jetson.

## 6. Next Steps
1.  **Firmware Development:** Implement the Constant Current Load logic on STM32.
2.  **AI Training:** Gather dataset of 18650 batteries (Normal vs Damaged) and train the classification model.
3.  **Mechanical Design:** Detail the stepper-motor hopper/sorting mechanism.
4.  **Integration:** Establish robust data exchange protocol between controllers.
