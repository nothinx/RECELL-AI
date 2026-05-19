# Rencana Implementasi: Sistem Klasifikasi Baterai RECELL-AI

**Proyek:** RECELL-AI
**Model AI:** YOLOv8n (Nano) & XGBoost
**Platform:** Jetson Orin Nano + STM32F411
**Target Waktu:** Kompetisi KIWIE Korea 2026

---

## Fase 1: Lingkungan & Setup AI (Jetson)
*Tujuan: Menjalankan YOLOv8n dan XGBoost dengan performa maksimal di Orin Nano.*

1.  **Persiapan Sistem:**
    *   Instalasi JetPack 6.x (Ubuntu 22.04).
    *   Instalasi Python 3.10, PyTorch (versi khusus Jetson), dan Ultralytics.
2.  **Optimasi Model (Vision):**
    *   Latih (Train) YOLOv8n menggunakan dataset khusus baterai (Normal, Karat, Penyok).
    *   **Ekspor ke TensorRT (`.engine`):** Langkah krusial ini memastikan inferensi berjalan pada 30+ FPS di Orin Nano.
3.  **Pipeline Visual:**
    *   Implementasikan *thread* kamera asinkron (menggunakan OpenCV/GStreamer).
    *   Buat fungsi *wrapper* deteksi yang mengembalikan "Skor Kesehatan Fisik".

---

## Fase 2: Pengembangan Firmware (STM32)
*Tujuan: Pembacaan sensor yang presisi dan eksekusi motor yang handal.*

1.  **Inisialisasi Periferal:**
    *   **ADC (12-bit) + Oversampling:** Untuk pembacaan tegangan dan arus berkecepatan tinggi dengan tingkat *noise* yang sangat minim.
    *   **PWM/Timers:** Untuk kontrol motor Stepper dan manajemen beban elektronik (Electronic Load).
    *   **UART (USB-CDC):** Untuk komunikasi Serial berkecepatan tinggi dengan Jetson.
2.  **Logika Inti:**
    *   Terapkan *loop* kontrol **Beban Arus Konstan (Constant Current Load)** menggunakan kontrol PWM.
    *   Hitung *Voltage Drop* untuk dikirim ke Jetson.
3.  **Eksekusi Perintah:**
    *   Buat *parser* (pembaca) JSON untuk perintah seperti `START_SOH`, `MOVE_CONVEYOR`, `EJECT_A`.

---

## Fase 3: Komunikasi & Protokol
*Tujuan: Pertukaran data yang cepat dan aman dari kegagalan (fail-safe).*

1.  **Definisi Protokol:** Menggunakan format paket terstruktur berbasis JSON (*Line-terminated*).
2.  **Handshake:** Memastikan Jetson dan STM32 memverifikasi koneksi (Ping) saat mesin dinyalakan.
3.  **Penanganan Error:** Menentukan perilaku sistem jika koneksi Serial terputus atau baterai tersangkut di konveyor (masuk ke mode aman/Safe Mode).

---

## Fase 4: Integrasi & Pengujian Mekanik
*Tujuan: Otomatisasi sistem secara penuh.*

1.  **Logika Sekuensial (Urutan Kerja):**
    *   `Langkah 1`: Jetson mengevaluasi Visi (YOLO) dan menyimpan skornya.
    *   `Langkah 2`: Konveyor membawa baterai menuju Stasiun Uji (berhenti di Proximity 1).
    *   `Langkah 3`: STM32 menempelkan sensor dan menjalankan uji Beban Arus Konstan -> Mengirim data kelistrikan ke Jetson.
    *   `Langkah 4`: Jetson menggunakan XGBoost untuk menghitung SoH, menggabungkan data, dan menentukan Grade Akhir.
    *   `Langkah 5`: Jetson mencetak Paspor Digital (PDF).
    *   `Langkah 6`: STM32 menyortir baterai (Eject ke Grade A di Proximity 2, atau biarkan jatuh untuk Grade B/Reject).
2.  **Penyetelan (Fine-tuning):** Menyesuaikan kecepatan motor stepper dan tingkat sensitivitas sensor batas (*limit sensors*).

---

## Fase 5: Dokumentasi & Penyempurnaan Akhir
*Tujuan: Kesiapan 100% untuk Kompetisi KIWIE.*

1.  **Dashboard Industri (HMI):** Menjalankan UI PyQt5 (dengan *live graphing* tegangan/arus menggunakan OpenGL) di layar penuh Jetson.
2.  **Pencatatan Data (Data Logging):** Jetson mencatat setiap hasil tes ke dalam *database* lokal/CSV sebagai bukti ketertelusuran industri (Traceability).
3.  **Dokumentasi Final:** Memperbarui Hak Kekayaan Intelektual (HKI) dan Spesifikasi Teknis dengan mencantumkan data pengujian dunia nyata.
