# Carollus — Computer Vision Module (RECELL-AI)

> Modul *machine vision* untuk **grading kondisi fisik baterai Li-Ion 18650 bekas**.
> Folder ini berdiri sendiri (self-contained) agar mudah di-*clone* dan dipresentasikan
> untuk tugas mata kuliah **Machine Vision & Pattern Recognition**.

---

## 1. Ringkasan

RECELL-AI adalah mesin penyortir baterai 18650 otomatis. Sistem lengkapnya
*multimodal* (Vision + Elektrik), tetapi **folder Carollus ini fokus HANYA pada bagian
Computer Vision**: bagaimana kamera menilai kondisi fisik permukaan baterai sebelum
diberi *grade* akhir (A / B / R).

Tugas vision dirumuskan sebagai **klasifikasi citra (image classification)**, bukan
deteksi objek. Setiap baterai yang lewat di konveyor difoto, lalu model menjawab satu
pertanyaan: *"Permukaan baterai ini termasuk kondisi apa?"*

| Indeks | Kelas    | Arti                                            | Implikasi grading      |
|:------:|----------|-------------------------------------------------|------------------------|
| 0      | `KARAT`  | Ada karat/korosi di kutub (+/–)                 | Defect → turun grade   |
| 1      | `KOSONG` | Slot kosong / tidak ada baterai                 | *Gate* → frame diabaikan |
| 2      | `SEHAT`  | Permukaan bersih & mulus                        | Kandidat **Grade A**   |
| 3      | `SOBEK`  | Wrapper plastik terkelupas/sobek                | Defect → turun grade   |

> **Kenapa ada kelas `KOSONG`?** Konveyor sering kosong di antara dua baterai.
> Kelas ini berfungsi sebagai *gate*: jika model memprediksi `KOSONG`, frame
> diabaikan sehingga sistem tidak menilai slot yang kosong.

---

## 2. Mengapa Klasifikasi, bukan Deteksi Objek?

Versi awal proyek memakai **deteksi objek** (bounding box: rust/dent/wrapper). Pendekatan
ini diganti ke **klasifikasi** karena:

1. **Posisi baterai terkontrol.** Baterai selalu berada di satu titik tetap di atas
   konveyor saat difoto (dipicu *proximity sensor*). Tidak perlu mencari *di mana*
   objeknya — cukup menilai *kondisinya*. Lokalisasi jadi mubazir.
2. **Anotasi jauh lebih murah.** Klasifikasi hanya butuh menaruh gambar ke folder per
   kelas. Tidak perlu menggambar ribuan bounding box.
3. **Lebih ringan & cepat.** Classifier `yolov8n-cls` di resolusi **224×224** jauh lebih
   ringan dari detektor 640×640 → FPS tinggi di edge device (Jetson Orin Nano).
4. **Top-1 sudah cukup.** Keputusan akhir hanya butuh satu label kondisi dominan, lalu
   digabung dengan skor elektrik (SoH) untuk grade final.

---

## 3. Arsitektur Model

- **Backbone:** YOLOv8n-cls (varian *nano* dari Ultralytics YOLOv8, mode *classify*).
- **Input:** RGB 224×224, dinormalisasi ke rentang [0, 1].
- **Output:** vektor probabilitas 4 kelas (via *softmax*), diambil **Top-1**.
- **Ukuran:** ±3 MB (`.pt`) — termasuk model yang sangat kecil, ideal untuk *edge*.

### Pipeline inferensi (end-to-end)
```
Foto baterai (BGR, OpenCV)
      │  resize 224×224
      ▼
BGR → RGB,  /255.0,  HWC → CHW,  tambah dim batch  → tensor 1×3×224×224
      ▼
Model (ONNX Runtime / PyTorch)  → logits 4 kelas
      ▼
softmax → argmax (Top-1) → label + confidence
      ▼
Jika label == KOSONG → abaikan frame
Selain itu → kirim sebagai "Vision Score" ke Decision Engine
```

### Transfer learning
Model dilatih dengan *transfer learning* dari bobot `yolov8n-cls.pt` (pra-latih di
ImageNet), lalu di-*fine-tune* pada dataset baterai. Ini membuat model konvergen cepat
walau datasetnya relatif kecil.

---

## 4. Dataset

Struktur folder (format **ImageFolder** — nama folder = label):
```
datasets/capture/
├── KARAT/    (±400 gambar)
├── KOSONG/   (±450 gambar)
├── SEHAT/    (±400 gambar)
└── SOBEK/    (±400 gambar)
```
Total ±1.650 gambar, diambil langsung dari kamera di atas konveyor (pencahayaan
menyerupai kondisi operasi: agak redup/berbayang). Kelas relatif **seimbang**, sehingga
akurasi menjadi metrik yang adil — tapi kita tetap melaporkan precision/recall/F1
per-kelas untuk transparansi.

> Urutan indeks kelas mengikuti **urutan alfabet folder** (KARAT, KOSONG, SEHAT, SOBEK),
> persis seperti yang dipakai Ultralytics saat training. Jangan diubah urutannya.

### Augmentasi
Saat training diaktifkan augmentasi standar Ultralytics (flip horizontal, perubahan
HSV/brightness, sedikit rotasi & translasi) agar model tahan terhadap variasi
pencahayaan dan orientasi baterai.

---

## 5. Hyperparameter Training

| Parameter   | Nilai            | Catatan                                  |
|-------------|------------------|------------------------------------------|
| Base model  | `yolov8n-cls.pt` | Pra-latih ImageNet                        |
| `imgsz`     | 224              | Resolusi standar classifier               |
| `epochs`    | 100              | Dengan `patience=20` (*early stopping*)   |
| `batch`     | 64               |                                           |
| Optimizer   | auto (SGD/AdamW) | Default Ultralytics                       |

Perintah training (referensi):
```bash
yolo classify train model=yolov8n-cls.pt data=datasets/capture imgsz=224 epochs=100 batch=64 patience=20
```

---

## 6. Konversi ke ONNX (membuat model lebih ringan)

`.pt` membutuhkan PyTorch + Ultralytics (berat, ratusan MB). Untuk **deploy** kita
konversi ke **ONNX** sehingga cukup berjalan di atas `onnxruntime` (jauh lebih kecil &
cepat, lintas platform).

```bash
pip install -r requirements.txt
python scripts/export_onnx.py --weights models/best_cls.pt --imgsz 224
# -> menghasilkan models/best_cls.onnx + models/classes.txt
```

> **Catatan untuk presentasi:** Konversi belum dijalankan di sini (sesuai permintaan,
> repo dikirim sebagai *starter kit*). Skrip `export_onnx.py` sudah siap — cukup jalankan
> sekali setelah `clone` untuk menghasilkan file `.onnx`. Untuk Jetson, ada langkah
> lanjutan ke TensorRT (`.engine`, FP16) yang menggandakan FPS.

Untuk produksi di Jetson Orin Nano:
```bash
yolo export model=models/best_cls.pt format=engine half=True imgsz=224   # -> .engine FP16
```

---

## 7. Deploy / Inferensi

**Ringan (disarankan, tanpa PyTorch):**
```bash
# satu gambar
python scripts/deploy_onnx.py --source sample_images/KARAT_sample.jpg
# satu folder
python scripts/deploy_onnx.py --source ../datasets/capture/SEHAT
# webcam realtime
python scripts/deploy_onnx.py --source 0 --show
```

**Verifikasi dengan PyTorch asli (lebih berat):**
```bash
python scripts/deploy_pt.py --source sample_images/SEHAT_sample.jpg
```

---

## 8. Visual Evaluasi (untuk presentasi)

Skrip `evaluate.py` menghasilkan semua visual sekaligus ke folder `results/`:

```bash
python scripts/evaluate.py --data ../datasets/capture --model models/best_cls.onnx --max-per-class 120
```

Yang dihasilkan:
- `confusion_matrix.png` — jumlah benar/salah antar kelas.
- `confusion_matrix_normalized.png` — recall per kelas (0–1).
- `per_class_metrics.png` + `.csv` — precision / recall / F1 / akurasi.
- `dataset_distribution.png` — jumlah gambar per kelas.
- `sample_predictions.png` — grid contoh prediksi + confidence (hijau=benar, merah=salah).
- `training_curves.png` — kurva loss/akurasi per epoch (butuh `results/results.csv` dari
  folder `runs/` hasil training Anda).

> Folder `results/` sudah berisi confusion matrix & kurva loss **bawaan dari training
> sebelumnya** (`conf_mat_recell.png`, `conf_mat_normalized.png`, `val_loss_recell.png`)
> sebagai cadangan jika Anda belum sempat menjalankan `evaluate.py`.

### Cara membaca confusion matrix
Baris = label **asli**, kolom = label **prediksi**. Diagonal = prediksi benar.
Sel di luar diagonal = kesalahan; misalnya nilai tinggi di baris `KARAT` kolom `SOBEK`
berarti model sering keliru menilai karat sebagai wrapper sobek (kedua defect ini memang
mirip secara visual — bahan diskusi yang bagus untuk presentasi).

---

## 9. Struktur Folder

```
carollus/
├── README.md                       ← dokumen ini
├── LAPORAN_Computer_Vision_RECELL.docx   ← laporan formal (untuk dikumpulkan)
├── requirements.txt
├── run_all.sh / run_all.bat        ← pipeline 1-klik
├── models/
│   └── best_cls.pt                 ← model terlatih (PyTorch, ±3 MB)
│       (best_cls.onnx & classes.txt dibuat setelah export_onnx.py)
├── scripts/
│   ├── export_onnx.py              ← konversi .pt → .onnx
│   ├── deploy_onnx.py              ← inferensi ringan (ONNX, tanpa PyTorch)
│   ├── deploy_pt.py                ← inferensi PyTorch (verifikasi)
│   └── evaluate.py                 ← semua visual evaluasi
├── sample_images/                  ← 1 contoh per kelas
└── results/                        ← confusion matrix, metrik, kurva, dll
```

---

## 10. Cara Cepat (setelah clone)

```bash
cd carollus
pip install -r requirements.txt
python scripts/export_onnx.py                 # buat best_cls.onnx
python scripts/evaluate.py --data ../datasets/capture   # buat semua visual
python scripts/deploy_onnx.py --source sample_images/SEHAT_sample.jpg
```
Atau cukup: `bash run_all.sh` (Linux/macOS) / `run_all.bat` (Windows).

---

## 11. Keterbatasan & Pengembangan

- Dataset diambil pada satu *setup* pencahayaan; performa bisa turun pada kondisi cahaya
  berbeda → perbanyak variasi data.
- Kelas defect `KARAT` vs `SOBEK` kadang mirip secara visual → pertimbangkan menambah data
  sulit (*hard examples*) atau resolusi input lebih tinggi.
- Model menilai *kondisi dominan*; baterai dengan dua cacat sekaligus hanya menghasilkan
  satu label. Untuk multi-label, beralih ke *multi-label classification*.
- Computer Vision di sini hanya **satu komponen**; grade akhir (A/B/R) ditentukan bersama
  skor elektrik (SoH dari model XGBoost).
