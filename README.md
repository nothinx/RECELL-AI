# 🔋 WORKSPACE GRADING BATERAI RECELL-AI
> **Sistem Klasifikasi Baterai Bekas (Second-Life) Otomatis Standar Industri**

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![C++](https://img.shields.io/badge/C++-%2300599C.svg?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![PyQt5](https://img.shields.io/badge/PyQt5-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-FF0000?style=for-the-badge&logo=yolo&logoColor=white)
![Industrial](https://img.shields.io/badge/Industry-4.0-blue?style=for-the-badge)

## 📂 Ringkasan Workspace

Monorepo ini mengelola seluruh pengembangan, pelatihan AI, dan *deployment firmware* untuk mesin penyortir baterai **RECELL-AI** yang dirancang untuk kompetisi KIWIE 2026.

| Modul | Deskripsi | Status |
| :--- | :--- | :--- |
| [**🧠 Jetson AI**](./jetson) | Mesin AI Multimodal (YOLOv8n + XGBoost), UI PyQT5, dan Orkestrasi. | `SIAP` |
| [**🦾 STM32 Firmware**](./firmware) | Pembacaan ADC 12-bit kecepatan tinggi dan kontrol motor Stepper via C++. | `SIAP` |
| [**🔬 Riset & Jurnal**](./research) | Whitepaper, Arsitektur AI, dan visualisasi data matplotlib. | `AKTIF` |

---

## 🔌 Pinout Perangkat Keras (STM32F411CEU6)

### Aktuator & Konveyor (Motor Driver BTS7960)
| Pin | Fungsi | Deskripsi |
| :--- | :--- | :--- |
| **PA5** | `CONVEYOR_EN` | Enable BTS7960 Motor Driver |
| **PA1** | `CONVEYOR_RPWM` | Right PWM (Maju) BTS7960 |
| **PA2** | `CONVEYOR_LPWM` | Left PWM (Mundur) BTS7960 |
| **PB0** | `STP_DRAIN_DIR` | Arah Stepper 1 (Drain Station) |
| **PB9** | `STP_DRAIN_PUL` | Pulsa Stepper 1 (Drain Station) |
| **PA7** | `STP_DRAIN_EN` | Enable / Encoder Stepper 1 (Drain Station) |
| **PA3** | `STP_SORT_DIR` | Arah Stepper 2 (Sorting Station) |
| **PA8** | `STP_SORT_PUL` | Pulsa Stepper 2 (Sorting Station) |
| **PA6** | `STP_SORT_EN` | Enable / Encoder Stepper 2 (Sorting Station) |

### Sensor, Limit Switch & Pengukuran
| Pin | Fungsi | Deskripsi |
| :--- | :--- | :--- |
| **PB15** | `LIMIT_DRAIN` | Limit switch batas gerak stepper Drain Station |
| **PA4** | `LIMIT_SORTING`| Limit switch batas gerak stepper Sorting Station |
| **PB14** | `IR_DRAIN` | Sensor Infra Merah pendeteksi baterai di Drain Station |
| **PB12** | `IR_SORTING` | Sensor Infra Merah pendeteksi baterai di Sorting Station |
| **PB13** | `IR_BACKUP` | Sensor Infra Merah Cadangan |
| **PB5** | `EMERGENCY` | Tombol Emergency Stop |
| **PB1** | `DAC_EN` | Kontrol Enable/Disable DAC (Constant Current Load) |
| **PB7** | `I2C SDA` | Jalur Data untuk INA226 (V/I), MLX90614 (Suhu Laser), MCP4725 (DAC) |
| **PB6** | `I2C SCL` | Jalur Clock untuk INA226 (V/I), MLX90614 (Suhu Laser), MCP4725 (DAC) |

---

## 🛠️ Stack Teknologi & Komponen

### 🖥️ Mesin Utama (Jetson Orin Nano)
*   **Framework:** Python 3.10+ dengan **PyQt5** & **pyqtgraph** (UI Akselerasi Perangkat Keras).
*   **AI Vision:** YOLOv8n dikompilasi ke TensorRT (`.engine`) untuk FPS maksimum.
*   **AI Analytics:** XGBoost Regressor untuk menginterpretasi kurva pengosongan Arus Konstan (SoH).
*   **Fitur Spesial:** Pembuatan Paspor Baterai Digital (PDF).

### 🦾 Firmware (STM32 BlackPill)
*   **Platform:** Arduino IDE (STM32duino Core).
*   **Pemrosesan Sinyal:** 
    *   Resolusi ADC bawaan 12-bit (4096 langkah).
    *   `Oversampling N=50` untuk menekan gangguan listrik (*noise filtering*).
*   **Komunikasi:** Payload JSON melalui USB-CDC Serial pada kecepatan 115200 bps.

---

## 🚀 Utilitas Mulai Cepat

Alat bantu cepat untuk *deployment* dan *training*:
- 📦 `setup.sh`: Skrip instalasi lingkungan 1-Klik untuk Jetson.
- 📉 `jetson/scripts/parse_nasa_mat.py`: Parser untuk mengubah dataset MATLAB NASA menjadi CSV yang siap digunakan AI.
- 🤖 `jetson/notebooks/`: Jupyter notebook yang dioptimalkan untuk pelatihan GPU di Google Colab.
- 📖 [**PANDUAN DEPLOYMENT**](./docs/DEPLOY_GUIDE_RECELL.md): Petunjuk lengkap untuk setup, *flashing*, dan SSH.
- 📐 [**CHEATSHEET RUMUS**](./docs/Cheatsheet_Rumus_SOH.md): Penjabaran Algoritma SOH Kelistrikan.

---

## 👨‍💻 Pengelola
**Amadeo Wisesa** - *System Architect & AI Engineer*
