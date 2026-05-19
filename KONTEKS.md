# PROYEK RECELL-AI: MASTER CONTEXT FILE
*(Dokumen ini dirancang khusus untuk dibaca oleh AI Assistant agar dapat langsung memahami state, arsitektur, dan tujuan proyek tanpa perlu membaca history percakapan panjang).*

## 1. IDENTITAS PROYEK
*   **Nama Proyek:** RECELL-AI
*   **Tujuan:** Mesin penyortir/grading baterai Li-Ion 18650 bekas secara otomatis untuk kompetisi KIWIE 2026.
*   **Target Kelas:** Grade A (Reusable), Grade B, Grade R (Recycle).
*   **Status Software (Saat ini):** 100% Selesai (Simulasi & Boilerplate). Menunggu perakitan Hardware.

## 2. ARSITEKTUR HARDWARE & SOFTWARE
Sistem ini menggunakan arsitektur **Master-Slave**:

### A. Master (NVIDIA Jetson Orin Nano)
*   **Fungsi:** Menjalankan GUI, model AI, dan mengambil keputusan (Decision Engine).
*   **Stack:** Python 3.10+, PyQt5 (GUI Hardware Accelerated dengan pyqtgraph), OpenCV.
*   **AI Vision:** **YOLOv8n** (diekskusi di TensorRT/DLA) untuk deteksi karat, penyok, bocor.
*   **AI Elektrik:** **XGBoost Regressor** untuk memprediksi State of Health (SoH) dari kurva Voltage Drop. Dataset menggunakan *NASA Battery Dataset* (parsed dari format `.mat`).

### B. Slave (STM32F411 BlackPill)
*   **Fungsi:** Mengeksekusi aktuator *real-time* dan membaca sensor dengan presisi tinggi.
*   **Stack:** C++ via Arduino IDE (Core STM32duino).
*   **Aktuator:**
    *   1x Motor DC/Stepper Konveyor (PWM lambat).
    *   1x Stepper Sensor (Mendorong pogo-pin/sensor elektrik ke kutub baterai).
    *   1x Stepper Ejector (Mendorong baterai Grade A ke bin khusus).
    *   1x MOSFET (Constant Current Load Test).
*   **Sensor:**
    *   2x Proximity Sensor (Prox 1 = Station Elektrik, Prox 2 = Station Ejector Grade A).
    *   2x ADC Pin (Voltage Sense & Current Sense) dijalankan di **12-bit Resolution dengan Oversampling 50x**.

### C. Protokol Komunikasi
*   **Medium:** USB-Serial (115200 baud rate).
*   **Format:** Line-terminated JSON (contoh: `{"cmd": "SORT", "grade": "A"}`).
*   Jetson mengirimkan *command* (aksi), STM32 membalas dengan status atau *telemetry* (voltase, arus).

## 3. WORKFLOW MEKANIK (AUTOMATED CYCLE)
Workflow ini diatur di fungsi `run_automated_cycle()` di `jetson/src/main.py`:
1.  **Vision Check:** Kamera Jetson memotret baterai di awal konveyor -> YOLO memberi *Vision Score* (0.0 - 1.0).
2.  **Feeding:** Jetson memerintahkan konveyor maju. Baterai menyentuh Prox 1 -> Konveyor stop.
3.  **Electrical Test:** STM32 memutar Stepper 1 untuk menempelkan pin -> Menyalakan MOSFET (Beban 1C) -> Mengukur V dan I dengan 12-bit ADC -> Menarik Stepper 1 mundur -> Mengirim V dan I ke Jetson.
4.  **Decision:** Jetson memasukkan nilai V dan I ke model XGBoost untuk memprediksi SOH%. Lalu menggabungkan *Vision Score* dan *SOH%* untuk mendapat Final Grade (A/B/R).
5.  **Passport Generation:** Jetson membuat file PDF (Digital Battery Passport) berisi foto baterai dan hasil tes.
6.  **Sorting:**
    *   Jika Grade A: Konveyor maju sampai Prox 2 -> Stop -> Stepper 2 Eject (2500 pulse).
    *   Jika Grade B/R: Konveyor maju terus sampai baterai jatuh di ujung (*End of Line*).

## 4. STRUKTUR DIREKTORI REPOSITORI
```text
RECELL-AI/
├── firmware/
│   └── RECELL_STM32/
│       └── RECELL_STM32.ino        (Source code STM32 siap flash)
├── jetson/
│   ├── datasets/                   (Tempat menaruh data NASA dan foto YOLO)
│   ├── models/                     (Tempat menaruh file .pt, .engine, .json XGBoost)
│   ├── notebooks/                  (Jupyter Notebook untuk training AI di Colab)
│   ├── scripts/                    (Script parser NASA .mat dan script training YOLO lokal)
│   └── src/
│       ├── main.py                 (Core logic & Serial Listener)
│       ├── ui_dashboard.py         (GUI PyQt5 Utama)
│       └── passport_generator.py   (Pembuat PDF)
├── research/
│   ├── paper_visuals/              (Script pembuat grafik untuk paper ilmiah)
│   ├── AI_PLAN.md                  (Roadmap AI mendetail)
│   ├── DEPLOYMENT_GUIDE.md         (Panduan SSH, Setup, Flash STM32)
│   └── kekurangan.md               (Kelemahan prototipe & saran komersialisasi)
└── setup.sh                        (1-Click install script untuk Jetson)
```

## 5. TUGAS SELANJUTNYA (HARDWARE & DATA PENDING)
Bagi AI selanjutnya yang mengambil alih proyek ini, fokus pada penyelesaian poin-poin berikut:
1.  **Hardware Binding:** Buka `RECELL_STM32.ino`, ubah angka/huruf PIN (contoh `PA0`, `PB10`) sesuai dengan kabel yang disolder oleh tim elektrikal.
2.  **YOLO Training:** User harus memotret baterai asli, menganotasi di Roboflow, lalu melatihnya menggunakan `Train_YOLOv8.ipynb`. Model `.pt` harus diekspor ke TensorRT `.engine` di Jetson.
3.  **XGBoost Training:** User harus mendownload data NASA (`.mat`), mengekstraknya dengan `parse_nasa_mat.py`, lalu melatih modelnya menggunakan `Train_XGBoost_NASA.ipynb`.
4.  **Uji Coba Live:** Matikan argumen `--sim` dan `--mock-ai` di `ui_dashboard.py`, lalu jalankan tes integrasi penuh.

**INSTRUKSI UNTUK AI SELANJUTNYA:**
Jika user meminta perbaikan, JANGAN merusak arsitektur *Multithreading/Callbacks* di `main.py` dan `ui_dashboard.py`. Pastikan komunikasi Serial tetap bersifat Non-Blocking. Jika UI *lag*, pastikan fungsi berat dipindahkan ke QThread atau module `threading` bawaan Python.
