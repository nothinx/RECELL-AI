# Jetson Orin Nano - AI Development & Training Guideline

Fokus utama pada Jetson adalah membangun "Otak" dari RECELL-AI. Karena kita menggunakan Multimodal AI (Vision + Time-Series), berikut adalah panduan komprehensif untuk pengembangannya.

---

## 1. Struktur Folder AI di Jetson
Pastikan Anda memiliki struktur direktori berikut di dalam proyek Jetson Anda untuk memanajemen *training* dan inferensi dengan rapi:

```text
jetson/
├── datasets/
│   ├── vision/          # Gambar baterai 18650
│   │   ├── images/      # (train, val, test)
│   │   └── labels/      # Format YOLO (.txt)
│   └── electrical/      # Data CSV kurva tegangan & arus
├── models/
│   ├── weights/         # File .pt (PyTorch) dan .json (XGBoost)
│   └── engines/         # File .engine (TensorRT untuk Orin Nano)
├── scripts/
│   ├── train_yolo.py    # Skrip untuk melatih YOLO
│   ├── train_xgb.py     # Skrip untuk melatih model Elektrik
│   └── export_trt.py    # Skrip untuk convert .pt ke .engine
└── src/
    └── ... (main.py, ui_dashboard.py)
```

---

## 2. Guideline Training: Computer Vision (YOLOv8n)

### A. Pengumpulan Data & Anotasi
1.  **Variasi Data:** Foto baterai dari berbagai *angle*, dengan pencahayaan yang mensimulasikan kondisi di atas konveyor (sedikit redup/berbayang).
2.  **Anotasi (Bounding Box):** Gunakan Roboflow/CVAT. 
    *   *Class 0:* `normal` (Baterai bersih).
    *   *Class 1:* `rust` (Bercak karat di kutub positif/negatif).
    *   *Class 2:* `dent` (Penyok pada body silinder).
    *   *Class 3:* `wrapper_damage` (Plastik pelindung terkelupas).
3.  **Format Export:** YOLOv8 PyTorch TXT.

### B. Hyperparameters Training (YOLOv8n)
Jika Anda men-*train* di PC/Google Colab sebelum dipindah ke Jetson:
*   **Epochs:** 300 (Gunakan *Early Stopping* di epoch 50 jika tidak ada perkembangan).
*   **Image Size:** 640 (Standar resolusi agar cepat di Edge).
*   **Batch Size:** 16 atau 32 (Tergantung VRAM GPU Anda).
*   **Augmentation:** Nyalakan `mosaic: 1.0`, `mixup: 0.2`, `degrees: 10.0` di file `data.yaml`.

### C. Ekspor ke TensorRT (SANGAT PENTING UNTUK JETSON)
Jangan menjalankan file `.pt` secara langsung di Jetson Orin Nano saat perlombaan/produksi, karena sangat lambat. Lakukan ekspor ke `.engine`:
```bash
# Jalankan ini DI DALAM Jetson Orin Nano
yolo export model=runs/detect/train/weights/best.pt format=engine half=True workspace=4
```
*(Catatan: `half=True` akan mengubah model ke FP16, meningkatkan FPS 2x lipat tanpa mengorbankan akurasi).*

---

## 3. Guideline Training: Electrical Time-Series (XGBoost)

Karena Jetson akan menerima data `voltage` dan `current` dari STM32, kita harus melatih AI Tabular.

### A. Format Dataset (CSV)
Setiap baris di CSV merepresentasikan 1 baterai yang sudah dites, contoh kolomnya:
| v_drop_max | v_recovery_1s | internal_res | temp_delta | **label_SOH** |
| :--- | :--- | :--- | :--- | :--- |
| 0.45 | 3.6 | 0.12 | 1.5 | 85.0 |
| 0.90 | 3.2 | 0.45 | 4.2 | 40.0 |

*Cara mendapatkan data ini:* Anda harus menjalankan purwarupa STM32, tes puluhan/ratusan baterai secara manual, catat nilainya ke CSV, dan tes kapasitas aslinya menggunakan *Capacity Tester* komersial (seperti LiitoKala) sebagai nilai kebenaran (*Ground Truth* / Label SoH).

### B. Proses Training (Scikit-Learn & XGBoost)
1.  **Normalisasi:** Lakukan `StandardScaler` pada fitur tegangan dan arus.
2.  **Model:** Gunakan `XGBRegressor` karena target kita adalah memprediksi angka (0-100%), bukan sekadar klasifikasi A/B/C.
3.  **Metrik Evaluasi:** Fokus tekan angka **RMSE (Root Mean Square Error)** serendah mungkin.

---

## 4. Pengembangan Lanjutan di Jetson (Next Steps)
Jika AI sudah siap, pengembangan di Jetson bisa difokuskan pada:
1.  **Multi-Threading UI & AI:** Menggabungkan kode OpenCV (YOLO) ke dalam antarmuka PyQt5 (`ui_dashboard.py`) agar bounding box tampil langsung di layar.
2.  **Database Integration:** Menambahkan kode SQLite di Jetson untuk menyimpan otomatis nilai YOLO dan nilai Elektrik setiap kali 1 siklus selesai.
