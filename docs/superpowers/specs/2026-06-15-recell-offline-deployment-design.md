# Spec B — Deployment Offline (Air-gapped Jetson Orin Nano Super) + Panduan SSH/scp

**Tanggal:** 2026-06-15
**Status:** Disetujui untuk perencanaan
**File terdampak:** `docs/DEPLOY_GUIDE_RECELL.md` (tulis ulang), `jetson/requirements-jetson-runtime.txt` (baru), `setup.sh` (versi offline)

---

## 1. Tujuan & kendala

Menyebarkan RECELL-AI ke **Jetson Orin Nano Super** yang **air-gapped (tidak pernah online)**.
Satu-satunya mesin yang sesekali online adalah **laptop Windows x86** milik user → berperan sebagai
mesin **staging** (unduh paket) dan **sumber transfer scp**.

**Target perangkat:** Jetson Orin Nano Super — JetPack 6.x, Ubuntu 22.04, aarch64, Python 3.10, CUDA 12.6.

**Kendala inti yang membentuk seluruh strategi:**
- Laptop x86 **tidak bisa** menjalankan/membangun wheel aarch64 secara native → harus pakai
  `pip download` dengan **platform tag aarch64**, dan untuk paket CUDA-spesifik ambil wheel
  **prebuilt Jetson** dari NVIDIA / jetson-ai-lab.
- Jetson air-gapped → **`apt` dan `pip` dari internet tidak tersedia**. Semua harus dari wheelhouse
  yang ditransfer.

## 2. Dependency runtime minimal (file baru)

`jetson/requirements-jetson-runtime.txt` — hanya yang dipanggil saat mesin berjalan
(dikonfirmasi dari import di `main.py`, `ui_dashboard.py`, `data_logger.py`, `passport_generator.py`):

```
ultralytics
torch
torchvision
opencv-python-headless
xgboost
pandas
numpy
PyQt5
pyqtgraph
pyserial
fpdf
```

Dibuang dari runtime (hanya untuk training/cloud, tidak dipakai mesin): `fastapi`, `uvicorn`,
`pydantic`, `pyyaml`, `paho-mqtt`, `SQLAlchemy`, `scikit-learn`, `scipy`, `matplotlib`, `seaborn`.
(`requirements.txt` lama tetap ada untuk lingkungan training.)

## 3. Strategi 3 tahap

### Tahap 1 — Staging di laptop (saat online)
1. Buat folder `wheelhouse/`.
2. Unduh wheel aarch64 dari PyPI:
   ```bash
   pip download --only-binary=:all: \
     --platform manylinux2014_aarch64 \
     --python-version 310 --implementation cp --abi cp310 \
     -d wheelhouse -r jetson/requirements-jetson-runtime.txt
   ```
3. **torch & torchvision** (perlu CUDA Jetson) tidak dari PyPI → unduh manual wheel prebuilt dari
   **jetson-ai-lab** (`https://pypi.jetson-ai-lab.dev/jp6/cu126`) atau index PyTorch-for-Jetson NVIDIA,
   simpan ke `wheelhouse/`.
4. **Risiko terdokumentasi:** sebagian paket mungkin hanya tersedia sebagai sdist sehingga gagal
   di-cross-download dari x86 (tidak ada wheel aarch64). Fallback: ambil versi prebuilt-nya dari
   jetson-ai-lab. Panduan menyertakan langkah verifikasi isi `wheelhouse/` sebelum transfer.

### Tahap 2 — Transfer via scp (panduan khusus Windows)
- Tooling: **Git Bash / OpenSSH bawaan Windows** (perintah `scp`, `ssh`).
- Cari IP Jetson; SSH aktif default di JetPack.
- Transfer seluruh proyek + wheelhouse:
  ```bash
  scp -r RECELL-AI/ <user>@<jetson-ip>:~/
  ```
- Panduan mencakup: cara cari IP Jetson, autentikasi password vs SSH key, transfer file besar
  (model `best.pt`, nanti `best.engine`), dan tips resume bila koneksi putus.

### Tahap 3 — Install di Jetson (offline)
1. Buat venv dengan akses ke paket sistem JetPack (OpenCV/CUDA bawaan), hindari masalah `apt` offline:
   ```bash
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   ```
   *(Bila modul `venv` tak tersedia, fallback: transfer wheel `virtualenv` ke wheelhouse dan pakai itu.)*
2. Install offline dari wheelhouse:
   ```bash
   pip install --no-index --find-links=./wheelhouse -r jetson/requirements-jetson-runtime.txt
   ```
3. One-time (offline, pakai ultralytics lokal): konversi `best.pt` → `best.engine` (TensorRT)
   untuk inferensi cepat di Jetson.
4. Opsional: buat `systemd` service agar dashboard autostart saat boot.

## 4. Penyesuaian runtime untuk offline

- Tidak ada panggilan jaringan saat runtime. MQTT/cloud sudah memang tidak dipakai di
  `main.py`/`ui_dashboard.py` → aman.
- Loader YOLO sudah memprioritaskan `best.engine` lalu fallback `best.pt` (lihat `main.py`) → cocok.

## 5. Struktur dokumen akhir

`docs/DEPLOY_GUIDE_RECELL.md` ditulis ulang dengan bagian:
1. Akses Jetson via SSH (cari IP, login, opsi Remote Desktop untuk GUI).
2. Staging dependency di laptop (Tahap 1).
3. Transfer scp (Tahap 2) — lengkap contoh Windows.
4. Install offline di Jetson (Tahap 3).
5. Flashing firmware STM32 (dari Arduino IDE / arduino-cli — diperbarui untuk `RECELL_STM32.ino` v2).
6. Menjalankan & autostart.
7. Troubleshooting (wheel hilang, serial port `/dev/ttyUSB0`, kamera).

`setup.sh` diperbarui jadi mode offline: `pip install --no-index --find-links=./wheelhouse` +
pembuatan folder data, tanpa `apt`/`pip` online.

## 6. Verifikasi

- Di laptop: pastikan `wheelhouse/` berisi wheel untuk **semua** entri runtime (skrip cek sederhana).
- Di Jetson: `pip install --no-index ...` selesai tanpa akses jaringan; `python -c "import torch; print(torch.cuda.is_available())"` → `True`.
- Jalankan `python src/ui_dashboard.py --sim` (tanpa STM32) lalu siklus penuh dengan STM32 terhubung.

## 7. Di luar cakupan (YAGNI)

- Membangun mirror PyPI internal / devpi.
- Containerisasi (Docker) — bisa jadi pekerjaan terpisah bila diperlukan.
- Setup training di Jetson (training dilakukan di mesin lain; Jetson hanya inferensi).
