# Analisis Kekurangan & Roadmap Komersialisasi (Software) - Enterprise Grade Breakdown

Dokumen ini merupakan pembedahan ekstrem (deep-dive breakdown) mengenai kekurangan arsitektur perangkat lunak RECELL-AI saat ini. Solusi yang ditawarkan dirancang untuk mencapai standar **Tier-1 Industrial Automation**, mengubah prototipe KIWIE menjadi produk komersial yang siap diproduksi massal (Mass Production Ready).

---

## 1. Enterprise Data Logging, Telemetry & Traceability
**Kondisi Saat Ini:** Tidak ada pencatatan data. Hasil grading (Vision Score dan SoH) hilang begitu saja setelah baterai disortir.
**Dampak Komersial:** Mesin tidak memenuhi standar ISO 9001 untuk ketertelusuran (traceability). Jika pembeli (pabrik daur ulang) mendapat komplain mengenai kualitas Grade A, mereka tidak punya bukti historis bahwa baterai tersebut telah lulus uji.

**Detail Solusi Teknis Drastis:**
*   **Local Time-Series Database:** Implementasikan **SQLite** (untuk versi ringan) atau **TimescaleDB** di Jetson Orin Nano untuk mencatat setiap milidetik data *discharge curve* (Voltage & Current).
*   **Unique Cell Identification:** Tambahkan modul *Barcode/QR Code Scanner* di stasiun *feeding*. Skema log di database:
    *   `battery_id` (Scanned QR / Auto-increment)
    *   `timestamp_start` & `timestamp_end`
    *   `vision_raw_score`, `detected_anomalies` (JSON array)
    *   `soh_score`, `internal_resistance`, `discharge_curve_blob`
    *   `final_grade`
*   **Structured Application Logging:** Gunakan pustaka logging terstruktur (contoh: `loguru` di Python). Log tidak boleh diprint ke konsol, melainkan ditulis ke file berotasi (`recell_sys_20260519.log`) dengan format JSON lines (`.jsonl`), mencakup metrik hardware Jetson (CPU/GPU Temp, RAM usage).

---

## 2. Keandalan Sistem & Penanganan Error (Hardened Fault Tolerance)
**Kondisi Saat Ini:** Alur kerja bersifat *blocking*. Gagalnya satu sensor akan membekukan seluruh sistem.
**Dampak Komersial:** Kerusakan mekanis pada mesin, risiko *thermal runaway* (baterai meledak), dan perlunya intervensi teknisi secara terus-menerus.

**Detail Solusi Teknis Drastis:**
*   **Binary RPC Protocol (Protobuf):** Tinggalkan JSON polos. Gunakan **Protocol Buffers (Protobuf)** atau **NanoPB** di STM32 untuk komunikasi serial. Ini menjamin integritas data dengan CRC/Checksum 16-bit dan memangkas overhead parsing string.
*   **Finite State Machine (FSM) dengan Timeout:** Setiap *state* di STM32 harus memiliki *Absolute Timeout*. Jika `STATE_SOH_MEASURING` tidak selesai dalam 3000ms, sistem paksa masuk ke `STATE_EMERGENCY_ABORT`.
*   **Dual-Layer Jamming Detection:** 
    1.  *Electrical:* Pembacaan ADC arus pada driver motor (mendeteksi *stall current*).
    2.  *Optical:* Rotary encoder atau optocoupler di ujung poros motor. Jika Jetson mengirim perintah jalan tapi encoder tidak membaca putaran = sabuk putus atau motor macet.
*   **Hardware Watchdog (IWDG):** Wajib diaktifkan di STM32 dengan interval 50ms.

---

## 3. Kalibrasi Otomatis & Manajemen Konfigurasi Dinamis
**Kondisi Saat Ini:** Ambang batas klasifikasi (SoH > 80%) di-*hardcode*.
**Dampak Komersial:** Mesin tidak fleksibel. Pabrik A mungkin menetapkan Grade A = 85%, Pabrik B menetapkan 75%. Teknisi harus merevisi kode untuk setiap pelanggan.

**Detail Solusi Teknis Drastis:**
*   **Dynamic Recipe Management:** Jetson memiliki *Local Web Server* (FastAPI). Supervisor pabrik dapat membuat "Sorting Recipes" (Resep Sortir). Contoh: Resep "Ketat" (SoH > 90%), Resep "Longgar" (SoH > 70%). Mesin dapat berganti resep tanpa *restart*.
*   **STM32 EEPROM Emulation & Auto-Zero:** Faktor kalibrasi sensor tegangan (Op-Amp offset) dan arus (Shunt offset) disimpan di sektor *Flash Memory* STM32. STM32 melakukan *Auto-zeroing* (kalibrasi nol) setiap kali mesin *idle* selama 5 menit.

---

## 4. Antarmuka Pengguna Industrial (HMI / UI/UX)
**Kondisi Saat Ini:** Hanya menggunakan Command Line Interface (CLI).
**Dampak Komersial:** Mesin terlihat seperti proyek mahasiswa, bukan perangkat industri seharga ribuan dolar.

**Detail Solusi Teknis Drastis:**
*   **Touchscreen HMI Panel:** Pasangkan layar sentuh industri 7" - 10" yang terhubung ke port HDMI/DP Jetson.
*   **Web-Based Kiosk UI (React/Vue + WebSocket):** 
    *   Tampilan *Live Feed* kamera (60 FPS via WebRTC) dengan *overlay bounding box* hijau/merah.
    *   Tampilan *Live Chart* (menggunakan ECharts/Chart.js) yang menggambar kurva penurunan tegangan secara *real-time* saat baterai diuji beban.
    *   Indikator OEE (Overall Equipment Effectiveness): *Throughput* baterai per jam.

---

## 5. IoT, Cloud Analytics & Predictive Maintenance
**Kondisi Saat Ini:** Mesin terisolasi (Offline).
**Dampak Komersial:** Perusahaan Anda tidak memiliki *recurring revenue* dari layanan *Data Analytics*. Pemilik mesin tidak bisa mengawasi pabriknya dari jauh.

**Detail Solusi Teknis Drastis:**
*   **Edge-to-Cloud Pipeline:** Jetson menjalankan *daemon* **Telegraf** atau agen kustom yang mengirim agregat data setiap 5 menit ke InfluxDB/AWS Timestream via protokol **MQTT** tersertifikasi TLS.
*   **Predictive Maintenance (AI on AI):** STM32 menghitung siklus aktuasi (contoh: Relay aktif 50.000 kali, Stepper berputar 1 juta step). Jetson menggunakan data ini untuk mengirim *Alert* ke Cloud: "Relay #2 diprediksi rusak dalam 10 hari, jadwalkan penggantian".

---

## 6. Optimasi AI & MLOps (Continuous Learning)
**Kondisi Saat Ini:** Model YOLOv8n bersifat statis.
**Dampak Komersial:** Akurasi menurun tajam jika desain kemasan (wrapper) baterai di pasaran berubah. Mesin menjadi usang.

**Detail Solusi Teknis Drastis:**
*   **Shadow Mode Detection:** Jetson menjalankan dua model. Model *Primary* (INT8 TensorRT) untuk eksekusi, dan Model *Shadow* untuk evaluasi. Jika hasil keduanya berbeda drastis, *frame* kamera tersebut disimpan (disimpan ke `/shadow_data/`).
*   **Automated Cloud Sync (MLOps):** Data anomali di-*zip* dan di-*upload* via AWS S3 / GCP pada pukul 02:00 pagi.
*   **INT8 DLA Acceleration:** Pindahkan eksekusi YOLOv8n dari GPU core Orin Nano ke **DLA (Deep Learning Accelerator)** core. Ini membebaskan GPU untuk tugas *rendering* UI dan pemrosesan video H.264, menurunkan suhu operasional mesin hingga 15°C.

---

## 7. Pembaruan Perangkat Lunak (OTA) & Keamanan (IP Protection)
**Kondisi Saat Ini:** Update manual dan *source code* terbuka.
**Dampak Komersial:** Pembajakan kekayaan intelektual (IP Theft) yang sangat masif. Algoritma rahasia Anda bisa dicuri hanya dengan melepas SD Card.

**Detail Solusi Teknis Drastis:**
*   **Full Disk Encryption (FDE) & Secure Boot:** Gunakan *Hardware Root of Trust* (RoT). OS Jetson dienkripsi menggunakan Luks, *key*-nya disimpan di dalam cip TPM/Tegra Security Enclave. Mesin tidak bisa di-*boot* dengan *kernel* modifikasi.
*   **Encrypted TensorRT Engine:** File `.engine` YOLO tidak ditaruh di *filesystem* terbuka. File ini di-dekripsi di dalam RAM menggunakan C++ wrapper khusus saat aplikasi berjalan.
*   **Containerized OTA Updates:** Gunakan layanan seperti **Balena/Mender** untuk manajemen OTA. Update firmware STM32 dikirim via kontainer Docker ke Jetson, lalu Jetson melakukan *flashing* (via YMODEM) ke STM32 secara otomatis di tengah malam, dengan fitur *Auto-Rollback* jika *flashing* gagal.
