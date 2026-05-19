# Rencana Arsitektur & Implementasi AI (RECELL-AI)

Untuk mencapai akurasi tingkat industri pada sistem RECELL-AI, pendekatan AI tidak boleh hanya bergantung pada satu model (Computer Vision). Kita harus menggunakan pendekatan **Multimodal AI** (Penggabungan Visual dan Data Sekuensial Elektrik). 

Berikut adalah rencana arsitektur AI komprehensif yang wajib diimplementasikan:

---

## 1. Computer Vision Pipeline (Inspeksi Fisik)
Bertujuan mendeteksi cacat fisik luar (karat, penyok, bocor, kerusakan insulasi/wrapper).

*   **Model Utama:** **YOLOv8n** (Ultralytics).
    *   *Alasan:* Keseimbangan terbaik antara kecepatan (FPS tinggi di Edge) dan akurasi.
*   **Kelas Deteksi (Classes):** `normal`, `rust_minor`, `rust_major`, `dent`, `wrapper_damaged`, `leaking`.
*   **Data Augmentation:** Karena lingkungan pencahayaan pabrik bisa berubah, augmentasi wajib dilakukan saat training:
    *   *Brightness/Contrast Shift*
    *   *Motion Blur* (mensimulasikan baterai yang bergerak di konveyor)
    *   *Rotation/Flip* (posisi baterai yang berguling).
*   **Akselerasi Hardware:** Model **wajib** diekspor ke format **TensorRT FP16 atau INT8** dan dieksekusi di **DLA (Deep Learning Accelerator)** Jetson Orin Nano, bukan di GPU utama, untuk menghemat daya dan menurunkan suhu mesin.

---

## 2. Time-Series Analysis (Inspeksi Elektrik / SoH)
Data yang dikirim dari STM32 (metode *Constant Current Load*) bukan sekadar angka statis, melainkan kurva *time-series* (Perubahan Tegangan & Arus terhadap Waktu).

*   **Pendekatan Tradisional (Baseline):** Menghitung *Internal Resistance* (IR) murni dengan rumus matematika $R = \Delta V / I$.
*   **Pendekatan AI Lanjutan (Machine Learning):**
    *   Kita menangkap *Array* tegangan selama 3 detik pembebanan (misal: 300 data points).
    *   **Feature Extraction:** Mengekstrak *slope* (kemiringan), *voltage bounce-back* (pemulihan tegangan setelah beban dilepas), dan *temperature delta*.
    *   **Model Rekomendasi:** **XGBoost** atau **Random Forest**.
    *   *Alasan:* Untuk data tabular terstruktur dari kurva *discharge* pendek, XGBoost sangat ringan, sangat akurat, dan tidak butuh *resource* GPU seperti Deep Learning. Algoritma ini akan memprediksi skor SoH (0-100%).

---

## 3. Sensor Fusion / Decision Engine (Penentuan Grade)
Setelah *Vision Score* (dari YOLO) dan *Electrical Score* (dari XGBoost) didapatkan, kita butuh "Hakim" penentu akhir.

*   **Pendekatan:** **Rule-Based Expert System** (Skrip Logika).
    *   Tidak perlu AI yang rumit di sini. Kita menggunakan pohon keputusan pasti (Deterministic Decision Tree) demi alasan keamanan (Safety).
    *   *Aturan Keselamatan Mutlak:* JIKA YOLO mendeteksi `leaking` (bocor) ATAU XGBoost mendeteksi `voltage_drop_extreme` (indikasi internal *short-circuit*), MAKA Grade = **RECYCLE (R)**, abaikan parameter lain.
    *   *Aturan Normal:* Bobot 70% pada hasil Elektrik, 30% pada hasil Visual.

---

## 4. Software Stack & MLOps Pipeline
Agar sistem siap dikomersialisasikan, proses *training* dan *deployment* harus otomatis.

### A. Data Annotation & Management
*   **Platform:** **Roboflow** atau **CVAT** (Computer Vision Annotation Tool).
*   Gunakan alat ini untuk memberi kotak (*bounding box*) pada ribuan foto baterai cacat. Platform ini memudahkan ekspor data langsung ke format YOLO.

### B. Video Analytics Framework
*   **NVIDIA DeepStream SDK:** Jangan gunakan `cv2.VideoCapture` biasa berbasis CPU. Gunakan **DeepStream** (berbasis GStreamer).
*   *Alasan:* DeepStream memproses decoding video langsung dari kamera ke memori GPU secara *Zero-Copy*. Ini meningkatkan efisiensi pembacaan kamera di Jetson hingga 400% dibandingkan OpenCV standar.

### C. Continuous Learning (MLOps)
1.  **Data Drifting:** Saat mesin bekerja di pabrik, Jetson akan menjumpai merek baterai dengan warna/corak baru yang tidak ada di dataset awal.
2.  **Active Sampling:** Jika YOLO mengeluarkan *Confidence Score* tanggung (misal: 45%), Jetson menyimpan gambar tersebut.
3.  **Cloud Retraining:** Gambar dikirim ke server Cloud -> Dianotasi ulang oleh manusia -> Model YOLO di-*train* ulang secara berkala -> File `.engine` TensorRT baru dikirim balik ke Jetson via OTA (*Over-The-Air*).

---

## 5. Ringkasan Eksekusi (Langkah Kongkret)
1.  **Tahap 1 (Bulan 1):** Kumpulkan 1.000+ foto baterai 18650 (Berbagai merk, kondisi mulus, berkarat, penyok). Anotasi di Roboflow.
2.  **Tahap 2 (Bulan 1):** Train YOLOv8n, ekspor ke TensorRT `.engine`, jalankan via Python di Jetson Orin Nano.
3.  **Tahap 3 (Bulan 2):** Rekam 500+ kurva *discharge* baterai dari STM32 (simpan dalam CSV). Beri label manual (SoH Baik / Buruk). Train model **XGBoost** di laptop, lalu *deploy* model XGBoost (`.json`/`.pkl`) ke Jetson.
4.  **Tahap 4 (Bulan 3):** Gabungkan *script* YOLO dan XGBoost ke dalam satu alur *Decision Engine* menggunakan *framework* NVIDIA DeepStream.
