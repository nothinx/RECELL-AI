# Panduan Deployment RECELL-AI — Jetson Orin Nano Super (OFFLINE / Air-gapped)

Panduan lengkap men-*deploy* RECELL-AI ke perangkat produksi:
**Jetson Orin Nano Super** (JetPack 6.x, Ubuntu 22.04, aarch64, Python 3.10, CUDA 12.6) yang
**tidak pernah terhubung internet**, dan **STM32F411** (BlackPill).

Mesin satu-satunya yang sesekali online adalah **laptop Windows** Anda → berperan sebagai
**mesin staging** (mengunduh paket) sekaligus **sumber transfer `scp`**.

> **Alur besar:**
>
> | Langkah | Mesin | Internet? |
> |---|---|---|
> | 1. Bangun `wheelhouse/` | **LAPTOP** | **PERLU** |
> | 2. Transfer via `scp` | Laptop → Jetson | Tidak |
> | 3. Install offline | **JETSON** | **DILARANG** |
> | 4. Flash STM32 | **LAPTOP** | Tidak |
> | 5. Jalankan app | **JETSON** | **DILARANG** |

---

## 0. Cara cepat — skrip otomatis

> **`[LAPTOP — ONLINE]`** Bangun wheelhouse dulu (sekali):
> ```bash
> bash laptop/prepare.sh
> ```
> Ikuti instruksi unduh manual torch/torchvision dari `https://pypi.jetson-ai-lab.dev/jp6/cu126`.

Setelah `wheelhouse/` lengkap, seluruh deploy bisa satu perintah dari laptop (Git Bash / Linux / macOS):

```bash
bash deploy/deploy.sh                  # target default: r2c@r2c.local, ~/RECELL-AI
bash deploy/deploy.sh user@host dir    # target lain
```

`deploy/deploy.sh` otomatis: (1) buat & salin SSH key (password Jetson diminta **sekali**, tak disimpan), (2) transfer proyek + `wheelhouse/` via tar-over-ssh, (3) jalankan `setup.sh` di Jetson.

`setup.sh` lalu install dependency offline **dan** memasang **systemd service `recell`** yang menjalankan GUI di monitor HDMI Jetson otomatis saat boot ke desktop (`graphical.target`, `DISPLAY=:0`). Lewati pemasangan service dengan `bash setup.sh --no-service`.

> **Syarat GUI autostart:** Jetson harus **auto-login ke desktop** (Settings → Users → Automatic Login). Tanpa sesi desktop aktif, service GUI tak punya display untuk digambar.

Perintah service di Jetson: `sudo systemctl start|status recell` · log realtime `journalctl -u recell -f`.

Sisanya (Tahap 1–7 di bawah) adalah rincian manual & troubleshooting dari langkah-langkah yang diotomatisasi skrip di atas.

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

> **`[LAPTOP — ONLINE]`** — Seluruh bagian ini hanya dijalankan di laptop yang terhubung internet.
> Jetson **tidak butuh dan tidak boleh** mengakses internet di tahap ini.

Tujuan: mengisi folder `wheelhouse/` dengan wheel **aarch64 / cp310** untuk semua dependency runtime.

> **Kenapa rumit?** Laptop Anda x86, Jetson aarch64. Kita tidak menjalankan paketnya di laptop —
> hanya **mengunduh** wheel untuk arsitektur Jetson, lalu memasangnya di Jetson.

### 2.1 Cara otomatis (disarankan)

```bash
bash laptop/prepare.sh
```

Skrip ini melakukan §2.2 dan §2.3 (onnx/onnxslim) secara otomatis, lalu menampilkan checklist
wheel yang sudah ada dan yang masih perlu diunduh manual (torch/torchvision/onnxruntime-gpu).

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

### 2.3 Unduh torch, torchvision & onnxruntime-gpu khusus Jetson (CUDA)

> **`[LAPTOP — ONLINE]`** — Unduh manual ke `wheelhouse/`, tidak bisa diotomatisasi.

`torch`/`torchvision`/`onnxruntime-gpu` **tidak** ada di PyPI sebagai build CUDA Jetson.
Ambil dari index **jetson-ai-lab** (cocokkan dengan JetPack 6 / CUDA 12.6 — `jp6/cu126`):

- Buka di browser laptop: `https://pypi.jetson-ai-lab.dev/jp6/cu126`
- Unduh file `.whl` untuk (pilih yang `cp310` / aarch64), simpan ke folder `wheelhouse/`:
  - **torch**
  - **torchvision**
  - **onnxruntime-gpu** ← dibutuhkan saat `yolo export format=engine` (konversi TensorRT offline)

> Referensi resmi PyTorch-for-Jetson juga ada di forum NVIDIA bila index di atas berubah.

### 2.4 Verifikasi isi wheelhouse SEBELUM transfer
```bash
ls wheelhouse | grep -iE 'torch|torchvision|ultralytics|opencv|xgboost|pandas|numpy|PyQt5|pyqtgraph|serial|fpdf'
```
Pastikan **torch**, **torchvision**, dan **onnxruntime-gpu** ADA (ketiganya dari jetson-ai-lab).
`laptop/prepare.sh` sudah melakukan pengecekan ini secara otomatis di akhir eksekusi.

> **Risiko jujur:** sebagian kecil paket mungkin hanya tersedia sebagai *sdist* (tanpa wheel
> aarch64) sehingga gagal di-`pip download` dari x86. Jika ada yang hilang:
> - cari versi prebuilt-nya di **jetson-ai-lab** dan unduh manual ke `wheelhouse/`, atau
> - pin versi lebih lama yang punya wheel aarch64 di `requirements-jetson-runtime.txt`, ulangi 2.2.

---

## 3. Tahap 2 — Transfer ke Jetson via `scp` (dari Windows)

> **`[LAPTOP → JETSON]`** — Dari laptop ke Jetson via jaringan lokal. Tidak ada internet di jalur ini.

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

> **`[JETSON — OFFLINE]`** — Seluruh bagian ini dijalankan di Jetson via SSH. Tidak ada perintah
> yang membutuhkan internet. Semua instalasi dari `wheelhouse/` lokal.

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

> **`[JETSON — OFFLINE]`** — Perintah ini dijalankan di Jetson. Tidak butuh internet **asalkan**
> `onnx`, `onnxslim`, dan `onnxruntime-gpu` sudah ada di `wheelhouse/` dan sudah terinstall
> oleh `setup.sh`. Bila belum, `yolo export` akan mencoba mengunduh dari internet dan **gagal**.

Untuk inferensi cepat di Jetson, ubah `best.pt` → `best.engine` (memakai ultralytics lokal):
```bash
source venv/bin/activate
cd ~/RECELL-AI/jetson
yolo export model=models/weights/best.pt format=engine device=0
# hasil best.engine -> letakkan di models/weights/ ; main.py otomatis memilihnya bila ada
```

Jika `yolo export` error dengan pesan "No matching distribution" untuk onnx/onnxruntime-gpu:
kembali ke laptop, unduh wheel yang kurang dari `https://pypi.jetson-ai-lab.dev/jp6/cu126`,
transfer ke `wheelhouse/`, lalu jalankan `pip install --no-index --find-links=./wheelhouse onnx onnxslim onnxruntime-gpu` di Jetson.

### Autostart saat boot (produksi)
**`setup.sh` sudah memasang & meng-enable service ini otomatis** (lihat §0). Unit yang
dibuat (`/etc/systemd/system/recell.service`) — path & user diisi otomatis dari sesi:
```ini
[Unit]
Description=RECELL-AI Battery Grading Dashboard
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=<user_jetson>
WorkingDirectory=/home/<user_jetson>/RECELL-AI/jetson/src
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/<user_jetson>/.Xauthority
ExecStart=/home/<user_jetson>/RECELL-AI/venv/bin/python ui_dashboard.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
```
GUI butuh sesi X aktif → unit pakai `graphical.target` + `DISPLAY=:0` + `XAUTHORITY`,
dan **Jetson harus auto-login ke desktop** agar layar HDMI tergambar saat boot.
Pasang ulang manual bila perlu: `bash setup.sh` (atau `--no-service` untuk melewati).

---

## 5. Flashing Firmware STM32 (dari laptop)

> **`[LAPTOP — ONLINE opsional]`** — Arduino IDE perlu internet pertama kali untuk mengunduh board
> package STM32. Setelah board package terinstall, flashing tidak butuh internet.

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
**`/dev/ttyACM0`** (STM32 USB CDC; bukan `ttyUSB0` yang untuk adapter FTDI/CH340).
`main.py` auto-deteksi ACM lalu USB, jadi biasanya tak perlu ubah `SERIAL_PORT`.

---

## 6. Menjalankan

> **`[JETSON — OFFLINE]`** — Semua perintah di bawah dijalankan di Jetson. Tidak ada internet dibutuhkan.

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
| YOLO load lambat (delay 10-30 detik) di Jetson | ultralytics telemetry masih mencoba koneksi. Jalankan: `source venv/bin/activate && python -c "from ultralytics import settings; settings.update({'sync': False})"` |
| `yolo export` error saat konversi TensorRT | onnx/onnxslim/onnxruntime-gpu tidak ada di `wheelhouse/`. Unduh dari `https://pypi.jetson-ai-lab.dev/jp6/cu126`, transfer, `pip install --no-index --find-links=./wheelhouse onnx onnxslim onnxruntime-gpu`. |
| `torch.cuda.is_available()` → `False` | Wheel torch bukan build CUDA Jetson. Ganti dengan wheel dari `jetson-ai-lab.dev/jp6/cu126` yang cocok JetPack Anda. |
| STM32 pill **OFFLINE** | Cek port ada (`ls /dev/ttyACM* /dev/ttyUSB*`); STM32 biasanya `ttyACM0` (auto-deteksi). Pastikan user di grup `dialout` (`sudo usermod -aG dialout $USER`, lalu re-login). Atau klik pill STM32 → pilih port manual. |
| Kamera/YOLO terasa delay/lag | Sudah dioptimasi (imgsz 320, buffer 1, capture 640×480). Masih berat? Export TensorRT engine (`best.engine`, lihat Bagian 4) — jauh lebih cepat di Jetson. Atau turunkan `YOLO_IMGSZ` di `main.py`. |
| Vision cuma deteksi 1 kelas (mis. SOBEK) | Isu model/training (kelas tak seimbang atau beda kondisi kamera vs data latih), bukan bug kode. Coba ubah `YOLO_CONF` di `main.py`; solusi tuntas = latih ulang dgn data seimbang & kondisi kamera sama. |
| Kamera tidak terdeteksi | `ls /dev/video*`; coba index lain di `cv2.VideoCapture(0)`; pastikan kamera USB terpasang. |
| GUI tak muncul lewat SSH | Pakai NoMachine/Remote Desktop atau monitor HDMI — bukan SSH biasa. |
| Stepper bergerak ke arah salah | Tukar `DIR_FORWARD`/`DIR_HOME` di `RECELL_STM32.ino`, atau verifikasi via `STEPPER_TEST`. |
| Konveyor / alat bergerak terlalu cepat | Buka panel **Kalibrasi** (tombol ⚙ KALIBRASI di layar atau **F12**), turunkan *Conveyor speed*, tekan **Simpan & Tutup**. Lihat Bagian 9. |

---

## 8. Ringkasan dependency

- **Produksi/offline (mesin):** `jetson/requirements-jetson-runtime.txt` — ramping, tanpa
  MQTT/cloud/FastAPI (tidak dipakai runtime).
- **Training (mesin lain, online):** `jetson/requirements.txt` — lengkap (xgboost, sklearn, scipy,
  matplotlib, dll) untuk melatih YOLO/XGBoost. Tidak perlu di Jetson produksi.

---

## 9. Update versi baru + Panel Kalibrasi

### 9.1 Update — TIDAK perlu install ulang
Tidak ada *library* baru pada update kalibrasi ini, jadi `venv` lama tetap dipakai.
```bash
cd ~/RECELL-AI
git pull                      # kode + model best.pt terbaru ikut otomatis
```
Yang **wajib** hanya **re-flash firmware STM32** (lihat Bagian 5), karena logika
kecepatan motor diubah: `CONVEYOR_SPEED`/`STEPPER_PULSE_US` kini variabel runtime
plus perintah `SET_CONFIG` & `JOG_FWD` yang dipakai panel kalibrasi.

### 9.2 Panel Kalibrasi (setup kecepatan)
Saat trial, konveyor over-shoot sensor IR walau PWM 30. Kecepatan sekarang
disetel **langsung dari layar tanpa re-flash**.

Konveyor juga punya **soft-start** otomatis (PWM naik bertahap ~300 ms) agar belt
tak menyentak & baterai tidak over-shoot sensor. Nilai aktif terlihat di kartu
*Conveyor Control* (baris "Kalibrasi: speed … · pulse … µs").

**Buka:** klik tombol **⚙ KALIBRASI** di kartu *Conveyor Control*, **atau** tekan **F12**.

| Parameter | Arti | Saran |
|---|---|---|
| **Conveyor speed (PWM 0–255)** | Kecepatan motor konveyor BTS7960. | Mulai **25**, turunkan bila masih cepat. |
| **Stepper pulse (µs)** | Jeda pulsa stepper. **Makin besar = makin pelan.** | Default **50**. Naikkan bila stepper terlalu cepat/kasar. |

Tombol:
- **▶ Jog Forward / ■ Stop** — uji jalan konveyor dengan nilai yang sedang diisi (tanpa siklus penuh). Pakai untuk cari kecepatan pas. Jog otomatis berhenti setelah 10 detik bila Stop lupa ditekan.
- **Apply (live)** — kirim ke STM32 sekarang, belum disimpan.
- **Simpan & Tutup** — kirim **dan** simpan ke `jetson/calibration.json`.

### 9.3 Nilai tersimpan permanen (tanpa EEPROM)
Nilai yang di-*Simpan* masuk ke `jetson/calibration.json` dan **otomatis dikirim
ulang ke STM32 setiap program start / serial reconnect**. Jadi sekali kalibrasi,
kecepatan tetap walau Jetson/alat di-*restart* — EEPROM di STM32 tidak diperlukan
karena alat selalu dikendalikan Jetson.
