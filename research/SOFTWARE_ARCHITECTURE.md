# Desain Arsitektur Perangkat Lunak: RECELL-AI

**Proyek:** Sistem Klasifikasi Baterai RECELL-AI
**Master (Pusat Kendali):** Jetson Orin Nano (AI, Logika, Antarmuka UI)
**Slave (Perangkat Keras):** STM32F411 (Sensor, Aktuator, Kendali Gerak)
**Komunikasi:** USB-Serial (direkomendasikan 115200 bps)

---

## 1. Alur Sistem Tingkat Tinggi (High-Level Flow)
1. **Pemicu (Trigger):** Baterai masuk ke stasiun pengujian (dideteksi oleh sensor Proximity).
2. **Fase Visual (Jetson):** Mengambil gambar -> Menjalankan Inferensi AI -> Mendeteksi anomali fisik.
3. **Fase Elektrik (STM32):** Menerapkan beban konstan (Load) -> Mengukur Tegangan/Arus secara presisi -> Mengirim data ke Jetson.
4. **Fase Keputusan (Jetson):** Menggabungkan data Visual (YOLO) + Elektrik (XGBoost) -> Menentukan Grade (A/B/Recycle) -> Mencetak Paspor PDF.
5. **Aksi (STM32):** Jetson mengirim perintah sortir -> STM32 mengaktifkan mekanisme Motor Stepper.

---

## 2. Arsitektur Jetson Orin Nano (Master)
Perangkat lunak Jetson berbasis Python agar fleksibel dengan berbagai library AI modern.

### Modul Utama:
*   **Mesin Visual (Vision Engine):** OpenCV + TensorRT (Inferensi). Memproses siaran langsung dari kamera.
*   **Manajer Komunikasi:** Menangani input/output Serial (PySerial) dengan format JSON.
*   **Mesin Prediksi Elektrik:** XGBoost Regressor untuk memprediksi State of Health (SoH).
*   **Antarmuka Pengguna (UI):** PyQt5 dengan PyQTGraph (Akselerasi OpenGL) untuk pemantauan *real-time*.
*   **Koordinator Utama (Orchestrator):** Alur kerja asinkron (*Multithreading*) yang mengatur perpindahan State.

---

## 3. Arsitektur STM32F411 (Slave)
Firmware STM32 berbasis C++ (Arduino IDE / STM32duino) dengan fokus pada waktu eksekusi yang deterministik.

### Tugas Utama:
*   **State Machine (Mesin Status):**
    *   `IDLE`: Menunggu perintah dari Jetson.
    *   `STATE_WAIT_PROX_1 / 2`: Konveyor berjalan pelan menunggu baterai menyentuh sensor.
    *   `MEASURING`: Menempelkan pin sensor, mengontrol beban MOSFET (Constant Current), dan membaca ADC 12-bit dengan teknik Oversampling 50x.
    *   `SORTING`: Mengeksekusi urutan langkah (*steps*) motor stepper dengan cepat.

---

## 4. Struktur Direktori Implementasi (Monorepo)
```text
RECELL-AI/
├── docs/                   # Cheatsheet rumus & Panduan Deployment
├── firmware/
│   └── RECELL_STM32/       # Kode C++ untuk Arduino IDE (.ino)
├── jetson/
│   ├── datasets/           # Data mentah untuk training (Gambar & CSV)
│   ├── models/             # Bobot (weights) YOLO & XGBoost yang sudah dilatih
│   ├── notebooks/          # Skrip Google Colab (.ipynb)
│   ├── scripts/            # Skrip utilitas (Data parser, Trainer)
│   └── src/                # Kode sumber utama Python (main.py, ui_dashboard.py)
├── research/               # Riset ilmiah, arsitektur, dan kode visualisasi grafik
└── setup.sh                # Skrip instalasi otomatis untuk OS Jetson
```
