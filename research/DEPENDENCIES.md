# RECELL-AI Full Dependency & Library Stack

Dokumen ini merinci seluruh pustaka (*library*), *framework*, dan *System-Level Dependencies* yang wajib dipersiapkan untuk lingkungan pengembangan (Jetson) maupun mikrokontroler (STM32).

---

## 1. Jetson Orin Nano (Master / AI)

### A. System-Level Dependencies (OS & Drivers)
*Package ini tidak bisa diinstall lewat `pip`, harus via `apt` atau NVIDIA SDK Manager.*
*   **NVIDIA JetPack 6.x:** OS dasar (Ubuntu 22.04) yang mencakup CUDA, cuDNN, dan TensorRT.
*   **TensorRT 8.6+:** Wajib untuk mengkuantisasi dan mengeksekusi model YOLOv8n ke format `.engine`.
*   **NVIDIA DeepStream SDK 6.3+:** *Framework* pipeline video berbasis GStreamer untuk akselerasi kamera *Zero-Copy*.
*   **SQLite3:** Database bawaan Linux untuk *local data logging*.

### B. Python Libraries (`requirements.txt`)
Berada di folder `jetson/requirements.txt`. Library utamanya meliputi:
*   **AI Vision:** `ultralytics` (YOLOv8).
*   **AI Electrical:** `xgboost`, `scikit-learn`, `pandas` (Prediksi Kurva).
*   **Web & Config:** `fastapi`, `uvicorn`, `pyyaml` (GUI Backend & Config).
*   **IoT & Comm:** `pyserial`, `paho-mqtt` (Komunikasi ke STM32 & Cloud).
*   **Logging:** `loguru` (Rotasi log berstandar enterprise).

---

## 2. STM32F411 (Slave / Hardware)

Pengembangan dilakukan di **STM32CubeIDE** atau **PlatformIO** (VSCode).

### A. Core Firmware Libraries
*   **STM32Cube HAL (Hardware Abstraction Layer):** Library resmi STMicroelectronics untuk mengontrol GPIO, ADC, Timer (PWM), DMA, dan UART.
*   **FreeRTOS (Opsional namun Sangat Direkomendasikan):** Sistem Operasi Real-Time. Digunakan agar *task* pembacaan sensor (ADC), penerimaan perintah (UART), dan penggerak motor (Stepper) berjalan secara paralel (*multithreading* di mikrokontroler).

### B. External C/C++ Libraries (Middleware)
*   **NanoPB (Protocol Buffers for Microcontrollers):**
    *   *Fungsi:* Menggantikan JSON polos. Melakukan enkripsi/dekripsi data serial (V, I, SoH) ke format biner yang sangat ringan, cepat, dan memiliki *checksum*.
    *   *Link:* [https://jpa.kapsi.fi/nanopb/](https://jpa.kapsi.fi/nanopb/)
*   **YMODEM Protocol Library (Untuk OTA):**
    *   *Fungsi:* Library di sisi *bootloader* STM32 agar bisa menerima file `firmware.bin` terbaru langsung dari Jetson via kabel Serial.

---

## 3. Frontend / UI (Opsional - Dashboard Kiosk)
Jika Anda menggunakan web-browser di layar sentuh Jetson:
*   **React.js atau Vue.js:** *Framework* antarmuka.
*   **ECharts / Chart.js:** Library untuk menggambar grafik kurva tegangan (*discharge curve*) secara *real-time* di layar operator.
