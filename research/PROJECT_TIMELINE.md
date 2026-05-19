# RECELL-AI: Project Timeline & Estimation

**Estimasi Total Waktu:** ~30 Hari (4 Minggu)
**Fokus Dataset:** NASA Battery Dataset (Kaggle) untuk prediksi State of Health (SoH).

Penggunaan **NASA Battery Dataset** adalah keputusan yang sangat tepat. Dataset ini berisi data siklus pengisian/pengosongan (charge/discharge) dengan pembacaan tegangan, arus, suhu, dan kapasitas nyata (SoH) yang diukur dengan instrumen presisi tinggi. Ini akan menghemat waktu berminggu-minggu dibanding mengumpulkan data secara manual.

---

## Minggu 1: Fondasi Hardware & Mekanik (Hari 1 - 7)
*Fokus: Memastikan konveyor dan semua aktuator berjalan sesuai perintah.*
*   **Hari 1-2:** Pembuatan sirkuit elektrikal (MOSFET Load, Sensor ADC, Stepper Driver).
*   **Hari 3-4:** Integrasi pinout elektrikal ke dalam `RECELL_STM32.ino`.
*   **Hari 5-6:** Uji coba mekanik murni: Menjalankan Jetson CLI (`--mock-ai`) untuk mengetes urutan: maju -> stop (Prox 1) -> dorong sensor -> mundur -> maju -> stop (Prox 2) -> eject.
*   **Hari 7:** Evaluasi dan kalibrasi *delay* motor stepper agar halus.

## Minggu 2: Computer Vision AI (Hari 8 - 14)
*Fokus: YOLOv8n untuk inspeksi fisik luar.*
*   **Hari 8-9:** Pengambilan gambar baterai 18650 secara langsung di atas konveyor mesin Anda (dengan pencahayaan asli mesin).
*   **Hari 10-11:** Anotasi data menggunakan Roboflow (Kelas: normal, rust, dent, wrapper_damage).
*   **Hari 12-13:** Proses Training YOLOv8n di PC/Google Colab.
*   **Hari 14:** Ekspor model ke TensorRT (`.engine`) dan uji coba *Live Camera* di GUI Jetson.

## Minggu 3: Time-Series AI & NASA Dataset (Hari 15 - 21)
*Fokus: Membuat model Machine Learning (XGBoost) untuk membaca SoH.*
*   **Hari 15-16:** Mempelajari dan membersihkan (*Data Preprocessing*) NASA Battery Dataset dari Kaggle menggunakan Python Pandas.
*   **Hari 17-18:** Ekstraksi fitur (Mencari korelasi antara *Voltage Drop* dalam 2 detik pertama terhadap kapasitas asli/SoH).
*   **Hari 19-20:** Training model XGBoost dan ekspor model tersebut agar bisa digunakan oleh Jetson.
*   **Hari 21:** *Sensor Calibration* -> Memastikan tegangan ADC STM32 selaras/sama akuratnya dengan instrumen ukur yang dipakai NASA agar model XGBoost bekerja akurat di mesin nyata.

## Minggu 4: Integrasi Akhir & UI/UX (Hari 22 - 30)
*Fokus: Persiapan untuk penjurian KIWIE.*
*   **Hari 22-24:** Integrasi model YOLO dan XGBoost ke dalam sistem utama secara bersamaan.
*   **Hari 25-26:** Uji coba *Full Automated Cycle* berulang kali. Validasi hasil **Digital Battery Passport (PDF)**.
*   **Hari 27-28:** Finalisasi UI PyQt5 (Tampilan Dashboard, Grafik, dan Estetika).
*   **Hari 29-30:** *Stress Test* (menjalankan mesin 2 jam nonstop), dokumentasi akhir, dan pembuatan video untuk kompetisi.
