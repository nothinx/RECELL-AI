# Panduan Deployment RECELL-AI — Jetson Orin Nano Super (OFFLINE / Air-gapped)

Panduan lengkap men-*deploy* RECELL-AI ke perangkat produksi:
**Jetson Orin Nano Super** (JetPack 6.x, Ubuntu 22.04, aarch64, Python 3.10, CUDA 12.6) yang
**tidak pernah terhubung internet**, dan **STM32F411** (BlackPill).

Mesin satu-satunya yang sesekali online adalah **laptop Windows** Anda → berperan sebagai
**mesin staging** (mengunduh paket) sekaligus **sumber transfer `scp`**.

> **Alur besar:**
> 1. **Laptop (online):** unduh semua wheel aarch64 ke folder `wheelhouse/`.
> 2. **Laptop → Jetson (`scp`):** kirim proyek + `wheelhouse/`.
> 3. **Jetson (offline):** install dari `wheelhouse/` tanpa internet.
> 4. **Flash STM32** dari laptop, colok ke Jetson.

---

## 1. Akses Jetson via SSH

Jetson menjalankan Ubuntu. SSH dipakai untuk menjalankan perintah CLI & transfer file.
SSH aktif secara default di JetPack.

1. Sambungkan Jetson & laptop ke **jaringan lokal yang sama** (router/switch — tetap *tanpa*
   internet pun bisa, asalkan satu LAN). Bisa juga kabel Ethernet langsung laptop↔Jetson.
2. Cari IP Jetson (jalankan di Jetson via monitor/keyboard sekali): `ip addr` → cari `192.168.x.x`.
3. Dari laptop (Git Bash / PowerShell / CMD):
   ```bash
   ssh <user_jetson>@<ip_jetson>      # contoh: ssh recell@192.168.1.50
   ```

### GUI lewat jaringan
Program utama `ui_dashboard.py` adalah GUI PyQt5 — **tidak muncul** lewat SSH biasa.
- **Disarankan:** install **NoMachine** di Jetson & laptop (paket `.deb` aarch64 ditransfer via scp,
  diinstal sekali) → desktop Jetson penuh & lancar, termasuk video kamera YOLO.
- Alternatif: jalankan langsung di monitor HDMI yang menancap ke Jetson.
- `ssh -X` (X11 forwarding) bisa tapi **lambat & patah-patah** untuk video — hindari untuk produksi.

---

## 2. Tahap 1 — Staging dependency di laptop (saat online)

Tujuan: mengisi folder `wheelhouse/` dengan wheel **aarch64 / cp310** untuk semua dependency runtime.

> **Kenapa rumit?** Laptop Anda x86, Jetson aarch64. Kita tidak menjalankan paketnya di laptop —
> hanya **mengunduh** wheel untuk arsitektur Jetson, lalu memasangnya di Jetson.

### 2.1 Siapkan folder
```bash
cd RECELL-AI
mkdir -p wheelhouse
```

### 2.2 Unduh wheel aarch64 dari PyPI (paket umum)
Butuh Python + pip di laptop (versi berapa pun — kita pakai *platform tag*, bukan interpreter lokal):
```bash
pip download \
  --only-binary=:all: \
  --platform manylinux2014_aarch64 \
  --python-version 310 --implementation cp --abi cp310 \
  -d wheelhouse \
  -r jetson/requirements-jetson-runtime.txt
```
Ini mengambil wheel aarch64 untuk: `ultralytics`, `opencv-python-headless`, `xgboost`,
`pandas`, `numpy`, `PyQt5`, `pyqtgraph`, `pyserial`, `fpdf`, beserta dependency-nya.

### 2.3 Unduh torch & torchvision khusus Jetson (CUDA)
`torch`/`torchvision` **tidak** ada di PyPI sebagai build CUDA Jetson. Ambil dari index **jetson-ai-lab**
(cocokkan dengan JetPack 6 / CUDA 12.6 — `jp6/cu126`):

- Buka di browser laptop: `https://pypi.jetson-ai-lab.dev/jp6/cu126`
- Unduh file `.whl` untuk **torch** dan **torchvision** (pilih yang `cp310` / aarch64), simpan ke
  folder `wheelhouse/`.
- (Opsional) Bila ultralytics meminta `onnxruntime-gpu`, ambil juga dari index yang sama.

> Referensi resmi PyTorch-for-Jetson juga ada di forum NVIDIA bila index di atas berubah.

### 2.4 Verifikasi isi wheelhouse SEBELUM transfer
```bash
ls wheelhouse | grep -iE 'torch|torchvision|ultralytics|opencv|xgboost|pandas|numpy|PyQt5|pyqtgraph|serial|fpdf'
```
Pastikan **torch** dan **torchvision** ADA.

> **Risiko jujur:** sebagian kecil paket mungkin hanya tersedia sebagai *sdist* (tanpa wheel
> aarch64) sehingga gagal di-`pip download` dari x86. Jika ada yang hilang:
> - cari versi prebuilt-nya di **jetson-ai-lab** dan unduh manual ke `wheelhouse/`, atau
> - pin versi lebih lama yang punya wheel aarch64 di `requirements-jetson-runtime.txt`, ulangi 2.2.

---

## 3. Tahap 2 — Transfer ke Jetson via `scp` (dari Windows)

`scp` & `ssh` sudah tersedia di **Git Bash** dan **OpenSSH** bawaan Windows 10/11.

### 3.1 Kirim seluruh proyek (termasuk wheelhouse)
Dari folder induk di laptop (Git Bash):
```bash
scp -r RECELL-AI/ <user_jetson>@<ip_jetson>:~/
```
Ini menyalin kode + `wheelhouse/` + model `best.pt` ke `~/RECELL-AI` di Jetson.

### 3.2 Tips
- **File besar** (model/wheel): scp bisa lama. Pantau progres; `scp` menampilkan persentase.
- **Hanya update sebagian** (mis. setelah mengubah kode di laptop):
  ```bash
  scp jetson/src/main.py <user_jetson>@<ip_jetson>:~/RECELL-AI/jetson/src/main.py
  ```
- **Koneksi putus saat transfer besar?** Pakai `rsync` (lebih tahan & bisa resume) bila tersedia:
  ```bash
  rsync -avP RECELL-AI/ <user_jetson>@<ip_jetson>:~/RECELL-AI/
  ```
- **Autentikasi tanpa password berulang:** salin kunci publik sekali —
  `ssh-keygen` (di laptop) lalu `ssh-copy-id <user_jetson>@<ip_jetson>` (atau salin manual ke
  `~/.ssh/authorized_keys` di Jetson via scp).

---

## 4. Tahap 3 — Install di Jetson (offline)

SSH ke Jetson, lalu:
```bash
cd ~/RECELL-AI
bash setup.sh
```

`setup.sh` (versi offline) otomatis:
1. Membuat venv `--system-site-packages` (memakai OpenCV/CUDA bawaan JetPack, tanpa `apt` online).
2. Install `torch` & `torchvision` dari `wheelhouse/`.
3. Install sisa runtime dari `wheelhouse/` (`requirements-jetson-runtime.txt`).
4. Membuat folder data & memverifikasi `torch.cuda.is_available()`.

### Manual (bila ingin langkah per langkah)
```bash
cd ~/RECELL-AI
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --no-index --find-links=./wheelhouse torch torchvision
pip install --no-index --find-links=./wheelhouse -r jetson/requirements-jetson-runtime.txt
```

### Konversi model ke TensorRT (sekali, offline)
Untuk inferensi cepat di Jetson, ubah `best.pt` → `best.engine` (memakai ultralytics lokal):
```bash
source venv/bin/activate
cd ~/RECELL-AI/jetson
yolo export model=models/weights/best.pt format=engine device=0
# hasil best.engine -> letakkan di models/weights/ ; main.py otomatis memilihnya bila ada
```

### Autostart saat boot (opsional, produksi)
Buat service systemd `/etc/systemd/system/recell.service`:
```ini
[Unit]
Description=RECELL-AI Dashboard
After=multi-user.target

[Service]
Type=simple
User=<user_jetson>
WorkingDirectory=/home/<user_jetson>/RECELL-AI/jetson/src
ExecStart=/home/<user_jetson>/RECELL-AI/venv/bin/python ui_dashboard.py
Restart=on-failure
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
```
Aktifkan: `sudo systemctl enable --now recell.service`.

---

## 5. Flashing Firmware STM32 (dari laptop)

Firmware produksi: `firmware/RECELL_STM32/RECELL_STM32.ino` (v2 — mekanik teruji WORKFLOW_TEST).

### 5.1 Arduino IDE
1. **File → Preferences → Additional Boards Manager URLs**, tambahkan:
   `https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json`
2. **Tools → Board → Boards Manager** → install **"STM32 MCU based boards"**.
3. Konfigurasi **Tools**:
   - Board: **Generic STM32F4 series**
   - Board Part Number: **BlackPill F411CE**
   - U(S)ART Support: **Enabled (generic 'Serial')**
   - USB Support: **CDC (generic 'Serial' supersede U(S)ART)** ← penting agar serial ke Jetson lancar
   - Upload Method: **STM32CubeProgrammer (DFU)** atau **STLink**
4. **Sketch → Include Library → Manage Libraries**, install:
   **ArduinoJson**, **INA226_WE**, **Adafruit MLX90614 Library**, **Adafruit MCP4725**.

### 5.2 (Disarankan) Verifikasi pin & arah dulu
Sebelum flash firmware produksi, jalankan `firmware/STEPPER_TEST/` untuk konfirmasi pin mapping &
arah DIR motor di mesin Anda (lihat catatan di `firmware/WORKFLOW_TEST/README.md`). Bila arah
terbalik, tukar `DIR_FORWARD`/`DIR_HOME` di `RECELL_STM32.ino`.

### 5.3 Upload
1. Colok STM32 ke laptop via USB-C. (Mode DFU: tahan BOOT, tekan-lepas NRST, lepas BOOT.)
2. Klik **Upload**, tunggu "Done Uploading".

### 5.4 CLI alternatif (arduino-cli)
```bash
arduino-cli compile --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE firmware/RECELL_STM32
arduino-cli upload  --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE -p <port> firmware/RECELL_STM32
```

### 5.5 Pindah ke Jetson
Cabut STM32 dari laptop, colok ke port USB **Jetson**. Kernel Jetson akan memetakannya sebagai
`/dev/ttyUSB0` (atau `/dev/ttyACM0`). Pastikan cocok dengan `SERIAL_PORT` di `jetson/src/main.py`.

---

## 6. Menjalankan

```bash
cd ~/RECELL-AI/jetson/src
source ../../venv/bin/activate
python ui_dashboard.py            # GUI penuh (butuh display/Remote Desktop)
# atau:
python ui_dashboard.py --sim      # tanpa STM32 (uji UI & alur)
python ui_dashboard.py --mock-ai  # tanpa kamera/YOLO
```

Indikator status (pill di header) harus menyala: **CAMERA**, **STM32**, **YOLO**, **XGB**.
**STM32 = ONLINE** menandakan serial tersambung.

---

## 7. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `pip ... No matching distribution` saat offline install | Wheel paket itu tidak ada di `wheelhouse/`. Ulangi Tahap 1 untuk paket tsb (cek nama & versi aarch64/cp310), atau ambil dari jetson-ai-lab. |
| `torch.cuda.is_available()` → `False` | Wheel torch bukan build CUDA Jetson. Ganti dengan wheel dari `jetson-ai-lab.dev/jp6/cu126` yang cocok JetPack Anda. |
| STM32 pill **OFFLINE** | Cek `/dev/ttyUSB0` ada (`ls /dev/ttyUSB*`); sesuaikan `SERIAL_PORT` di `main.py`; pastikan user di grup `dialout` (`sudo usermod -aG dialout $USER`, lalu re-login). |
| Kamera tidak terdeteksi | `ls /dev/video*`; coba index lain di `cv2.VideoCapture(0)`; pastikan kamera USB terpasang. |
| GUI tak muncul lewat SSH | Pakai NoMachine/Remote Desktop atau monitor HDMI — bukan SSH biasa. |
| Stepper bergerak ke arah salah | Tukar `DIR_FORWARD`/`DIR_HOME` di `RECELL_STM32.ino`, atau verifikasi via `STEPPER_TEST`. |

---

## 8. Ringkasan dependency

- **Produksi/offline (mesin):** `jetson/requirements-jetson-runtime.txt` — ramping, tanpa
  MQTT/cloud/FastAPI (tidak dipakai runtime).
- **Training (mesin lain, online):** `jetson/requirements.txt` — lengkap (xgboost, sklearn, scipy,
  matplotlib, dll) untuk melatih YOLO/XGBoost. Tidak perlu di Jetson produksi.
