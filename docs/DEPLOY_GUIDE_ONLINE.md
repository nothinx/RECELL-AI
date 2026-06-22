# Panduan Deploy RECELL-AI — Jetson dengan Internet

Panduan ini untuk Jetson Orin Nano Super yang **bisa terhubung internet**.
Tidak perlu menyiapkan wheelhouse di laptop, tidak perlu scp.

---

## Alur

```
Laptop                        Jetson (ada internet)
------                        ---------------------
                              git clone → pip install → jalankan
```

Semua dilakukan langsung di Jetson. Laptop hanya dipakai untuk SSH masuk.

---

## 1. Sambungkan ke Jetson via SSH

```bash
ssh <user>@<ip_jetson>        # contoh: ssh recell@192.168.1.50
```

Cari IP Jetson: jalankan `ip addr` di Jetson (via monitor/keyboard pertama kali).

---

## 2. Clone proyek

```bash
git clone https://github.com/nothinx/RECELL-AI.git
cd RECELL-AI
```

Model `best.pt` dan `soh_xgb_model.json` sudah ikut di dalam repo — tidak perlu transfer manual.

---

## 3. Setup satu perintah

```bash
bash setup.sh --online
```

Skrip ini otomatis:
1. Membuat venv `--system-site-packages` (PyQt5 + OpenCV CUDA dari sistem JetPack)
2. Install `torch` + `torchvision` build CUDA dari index NVIDIA (`pypi.jetson-ai-lab.io`)
3. Install semua dependency runtime (`ultralytics`, `xgboost`, `pandas`, dll)
4. Install ONNX export deps (`onnx`, `onnxslim`, `onnxruntime-gpu`)
5. Matikan ultralytics telemetry (tidak ada HTTP call saat runtime)
6. Buat folder data (`jetson/data/`, `jetson/models/`)
7. Pasang & enable systemd service `recell` (GUI autostart saat boot ke desktop)

> **Lewati service:** `bash setup.sh --online --no-service`

---

## 4. Konversi model ke TensorRT (opsional, tapi disarankan)

Untuk inferensi lebih cepat di Jetson, konversi `best.pt` → `best.engine` sekali:

```bash
source venv/bin/activate
cd jetson
yolo export model=models/weights/best.pt format=engine device=0
```

`main.py` secara otomatis memilih `best.engine` bila ada, fallback ke `best.pt`.

---

## 5. Jalankan

```bash
cd ~/RECELL-AI/jetson/src
source ../../venv/bin/activate

python ui_dashboard.py            # GUI penuh (butuh display / Remote Desktop)
python ui_dashboard.py --sim      # tanpa STM32 (uji alur & UI)
python ui_dashboard.py --mock-ai  # tanpa kamera/YOLO
```

Service systemd sudah aktif — GUI akan muncul otomatis di layar HDMI saat boot ke desktop,
**asalkan Jetson disetel auto-login** (Settings → Users → Automatic Login).

---

## 6. GUI lewat jaringan

Program utama adalah GUI PyQt5 — tidak muncul lewat SSH biasa.

- **Disarankan:** install **NoMachine** (paket `.deb` aarch64, transfer via scp sekali)
  → desktop Jetson penuh & lancar, termasuk video kamera YOLO
- **Alternatif:** monitor HDMI langsung ke Jetson
- `ssh -X` bisa tapi lambat & patah-patah untuk video — hindari untuk produksi

---

## 7. Flash firmware STM32 (dari laptop)

Firmware: `firmware/RECELL_STM32/RECELL_STM32.ino`

1. Buka di **Arduino IDE** di laptop (bukan di Jetson)
2. Tools → Board → **Generic STM32F4 series**, Board Part Number → **BlackPill F411CE**
3. USB Support → **CDC (generic 'Serial' supersede U(S)ART)**
4. Upload Method → **STM32CubeProgrammer (DFU)**
5. Mode DFU: tahan BOOT, tekan-lepas NRST, lepas BOOT → klik Upload
6. Setelah upload, cabut dari laptop → colok ke USB Jetson → muncul sebagai `/dev/ttyUSB0`

---

## 8. Troubleshooting

| Gejala | Solusi |
|---|---|
| `torch.cuda.is_available()` → `False` | torch terinstall dari PyPI biasa (CPU). Cek: `pip show torch` → versi harus mengandung `+cu` atau `jetson`. Install ulang: `pip install torch torchvision --extra-index-url https://pypi.jetson-ai-lab.io/jp6/cu126` |
| STM32 **OFFLINE** di dashboard | `ls /dev/ttyUSB*` — pastikan ada. Cek user di grup dialout: `groups` → bila tidak ada, `sudo usermod -aG dialout $USER` lalu re-login |
| GUI tidak muncul saat boot | Pastikan auto-login aktif di Settings → Users. Cek: `sudo systemctl status recell` |
| YOLO load lama (>10 detik) | Matikan telemetry: `source venv/bin/activate && python -c "from ultralytics import settings; settings.update({'sync': False})"` |
| `yolo export` gagal | `pip install onnx onnxslim onnxruntime-gpu --extra-index-url https://pypi.jetson-ai-lab.io/jp6/cu126` |
| Kamera tidak terdeteksi | `ls /dev/video*` — coba index lain: `cv2.VideoCapture(1)` di `main.py` |

---

## Ringkasan dependency

| Paket | Sumber |
|---|---|
| `torch`, `torchvision`, `onnxruntime-gpu` | `pypi.jetson-ai-lab.io` (build CUDA Jetson) |
| `PyQt5`, `cv2` (OpenCV) | Sistem JetPack via `--system-site-packages` |
| Sisa (`ultralytics`, `xgboost`, `pandas`, dll) | PyPI biasa |
