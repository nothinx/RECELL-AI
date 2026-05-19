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

### Aktuator & Konveyor
| Pin | Fungsi | Deskripsi |
| :--- | :--- | :--- |
| **PA0** | `CONVEYOR_DIR` | Arah Motor Konveyor |
| **PA1** | `CONVEYOR_PWM` | Kecepatan Motor Konveyor (Timer PWM) |
| **PB10** | `STP_SENS_DIR` | Arah Stepper 1 (Pendorong Sensor) |
| **PB11** | `STP_SENS_STP` | Pulsa Stepper 1 (Pendorong Sensor) |
| **PB12** | `STP_SENS_EN` | Enable Stepper 1 (Pendorong Sensor) |
| **PA8** | `STP_EJCT_DIR` | Arah Stepper 2 (Ejector Grade A) |
| **PA9** | `STP_EJCT_STP` | Pulsa Stepper 2 (Ejector Grade A) |
| **PA10** | `STP_EJCT_EN` | Enable Stepper 2 (Ejector Grade A) |

### Sensor & Pengukuran
| Pin | Fungsi | Deskripsi |
| :--- | :--- | :--- |
| **PB0** | `PROX_1` | Sensor Jarak (Stasiun Uji) - Input Pullup |
| **PB1** | `PROX_2` | Sensor Jarak (Keranjang Grade A) - Input Pullup |
| **PA5** | `LOAD_PWM` | Kontrol Gerbang MOSFET untuk Arus Konstan |
| **PA6** | `VOLT_SENSE` | ADC Tegangan Baterai (12-bit) |
| **PA7** | `CURR_SENSE` | ADC Arus via Shunt (12-bit) |

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
