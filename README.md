# 🔋 RECELL-AI BATTERY GRADING WORKSPACE
> **Industrial-grade Automated Second-Life Battery Classification System**

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![C++](https://img.shields.io/badge/C++-%2300599C.svg?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![PyQt5](https://img.shields.io/badge/PyQt5-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-FF0000?style=for-the-badge&logo=yolo&logoColor=white)
![Industrial](https://img.shields.io/badge/Industry-4.0-blue?style=for-the-badge)

## 📂 Workspace Overview

This monorepo manages the development, AI training, and firmware deployment of the **RECELL-AI** battery sorting machine designed for the KIWIE 2026 competition.

| Module | Description | Status |
| :--- | :--- | :--- |
| [**🧠 Jetson AI**](./jetson) | Multimodal AI Engine (YOLOv8n + XGBoost), PyQT5 UI, and Orchestration. | `READY` |
| [**🦾 STM32 Firmware**](./firmware) | High-speed 12-bit ADC sensing and Stepper motor control via C++. | `READY` |
| [**🔬 Research & Papers**](./research) | Whitepapers, AI architectures, and matplotlib data visualizers. | `ACTIVE` |

---

## 🔌 Hardware Pinout (STM32F411CEU6)

### Actuators & Conveyor
| Pin | Function | Description |
| :--- | :--- | :--- |
| **PA0** | `CONVEYOR_DIR` | Conveyor Motor Direction |
| **PA1** | `CONVEYOR_PWM` | Conveyor Motor Speed (Timer) |
| **PB10** | `STP_SENS_DIR` | Stepper 1 (Sensor Pusher) Direction |
| **PB11** | `STP_SENS_STP` | Stepper 1 (Sensor Pusher) Step Pulse |
| **PB12** | `STP_SENS_EN` | Stepper 1 (Sensor Pusher) Enable |
| **PA8** | `STP_EJCT_DIR` | Stepper 2 (Grade A Ejector) Direction |
| **PA9** | `STP_EJCT_STP` | Stepper 2 (Grade A Ejector) Step Pulse |
| **PA10** | `STP_EJCT_EN` | Stepper 2 (Grade A Ejector) Enable |

### Sensors & Measurements
| Pin | Function | Description |
| :--- | :--- | :--- |
| **PB0** | `PROX_1` | Proximity Sensor (Test Station) - Input Pullup |
| **PB1** | `PROX_2` | Proximity Sensor (Grade A Bin) - Input Pullup |
| **PA5** | `LOAD_PWM` | MOSFET Gate Control for Constant Current |
| **PA6** | `VOLT_SENSE` | Battery Voltage ADC (12-bit) |
| **PA7** | `CURR_SENSE` | Current Shunt ADC (12-bit) |

---

## 🛠️ Tech Stack & Components

### 🖥️ Master Engine (Jetson Orin Nano)
*   **Framework:** Python 3.10+ with **PyQt5** & **pyqtgraph** (Hardware Accelerated UI).
*   **AI Vision:** YOLOv8n compiled to TensorRT (`.engine`) for maximum FPS.
*   **AI Analytics:** XGBoost Regressor to interpret Constant Current discharge curves.
*   **Feature:** Digital Battery Passport generation (PDF).

### 🦾 Firmware (STM32 BlackPill)
*   **Platform:** Arduino IDE (STM32duino Core).
*   **Signal Processing:** 
    *   12-bit native ADC resolution (4096 steps).
    *   `Oversampling N=50` to suppress electrical noise.
*   **Communication:** JSON payloads over USB-CDC Serial at 115200 bps.

---

## 🚀 Quick Start Utilities

Rapid tools for deployment and training:
- 📦 `setup.sh`: 1-Click environment installation script for Jetson.
- 📉 `jetson/scripts/parse_nasa_mat.py`: Parser to convert NASA's MATLAB dataset into AI-ready CSV.
- 🤖 `jetson/notebooks/`: Jupyter notebooks optimized for Google Colab GPU training.
- 📖 [**DEPLOYMENT GUIDE**](./docs/DEPLOY_GUIDE_RECELL.md): Comprehensive setup, flashing, and SSH instructions.
- 📐 [**MATH CHEATSHEET**](./docs/Cheatsheet_Rumus_SOH.md): Breakdown of the Electrical SOH Algorithm.

---

## 👨‍💻 Maintainer
**Amadeo Wisesa** - *System Architect & AI Engineer*
