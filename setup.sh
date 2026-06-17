#!/bin/bash
# ============================================================================
#  RECELL-AI — SETUP OFFLINE (Air-gapped Jetson Orin Nano Super)
# ----------------------------------------------------------------------------
#  Dijalankan DI JETSON, setelah seluruh proyek + folder wheelhouse/ ditransfer
#  via scp dari laptop (lihat docs/DEPLOY_GUIDE_RECELL.md).
#
#  TIDAK ada akses internet di sini: tanpa apt, tanpa pip online.
#  Semua paket diinstal dari ./wheelhouse (wheel aarch64 yang sudah ditransfer).
# ============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHEELHOUSE="$ROOT_DIR/wheelhouse"

echo "============================================="
echo " RECELL-AI OFFLINE SETUP (Jetson, air-gapped)"
echo "============================================="

# 0. Sanity check wheelhouse
if [ ! -d "$WHEELHOUSE" ]; then
  echo "[FATAL] Folder wheelhouse/ tidak ditemukan di $ROOT_DIR"
  echo "        Transfer dulu dari laptop: scp -r wheelhouse user@<jetson-ip>:~/RECELL-AI/"
  exit 1
fi

# 1. Virtual environment dengan akses paket sistem JetPack (OpenCV/CUDA bawaan)
#    --system-site-packages menghindari kebutuhan apt install python3-venv online.
echo "[*] Membuat virtual environment (--system-site-packages)..."
python3 -m venv --system-site-packages venv
source venv/bin/activate

# 2. Upgrade pip secara OFFLINE bila wheel pip tersedia di wheelhouse (opsional)
if ls "$WHEELHOUSE"/pip-*.whl >/dev/null 2>&1; then
  echo "[*] Upgrade pip dari wheelhouse..."
  pip install --no-index --find-links="$WHEELHOUSE" --upgrade pip
fi

# 3. Install torch & torchvision (build CUDA Jetson) LEBIH DULU dari wheelhouse
echo "[*] Install torch & torchvision (wheel CUDA Jetson)..."
pip install --no-index --find-links="$WHEELHOUSE" torch torchvision

# 4. Install sisa dependency runtime dari wheelhouse
echo "[*] Install dependency runtime dari wheelhouse..."
pip install --no-index --find-links="$WHEELHOUSE" -r jetson/requirements-jetson-runtime.txt

# 5. Matikan ultralytics telemetry (persists ke ~/.config/Ultralytics/settings.yaml)
#    Ini mencegah HTTP timeout saat YOLO pertama kali diload di Jetson air-gapped.
echo "[*] Matikan ultralytics telemetry (air-gapped)..."
python -c "from ultralytics import settings; settings.update({'sync': False})" || \
  echo "    [WARN] Gagal matikan telemetry — abaikan bila ultralytics belum terpasang (akan dicoba ulang saat runtime)."

# 5b. Pre-install ONNX export deps (opsional, untuk 'yolo export format=engine')
#     Tanpa ini, ultralytics mencoba pip install onnx/onnxslim dari internet saat export.
echo "[*] Pre-install ONNX export deps (untuk konversi TensorRT offline)..."
pip install --no-index --find-links="$WHEELHOUSE" onnx onnxslim 2>/dev/null && \
  echo "    + onnx, onnxslim terinstall." || \
  echo "    [INFO] onnx/onnxslim tidak ada di wheelhouse — tambahkan ke wheelhouse laptop jika ingin konversi TensorRT offline (lihat docs §4)."

# 6. Buat struktur folder data
echo "[*] Membuat folder data..."
mkdir -p jetson/data/passports
mkdir -p jetson/data/logs
mkdir -p jetson/models/weights
mkdir -p jetson/models/engines

# 7. Verifikasi CUDA torch
echo "[*] Verifikasi PyTorch + CUDA..."
python -c "import torch; print('torch', torch.__version__, '| CUDA tersedia:', torch.cuda.is_available())" || \
  echo "[WARN] Verifikasi torch gagal — cek wheel torch di wheelhouse cocok dgn JetPack/CUDA Jetson."

deactivate 2>/dev/null || true

# 8. Service systemd autostart (GUI di monitor HDMI Jetson)
#    Lewati dengan: bash setup.sh --no-service
if [ "${1:-}" = "--no-service" ]; then
  echo "[*] --no-service: lewati pemasangan systemd service."
else
  echo "[*] Memasang systemd service 'recell' (GUI autostart saat boot)..."
  SERVICE_USER="$(id -un)"
  SERVICE_FILE="/etc/systemd/system/recell.service"

  # Akses serial STM32 (/dev/ttyUSB0) tanpa sudo — butuh re-login agar efektif.
  sudo usermod -aG dialout "$SERVICE_USER" 2>/dev/null \
    && echo "    + $SERVICE_USER ditambahkan ke grup dialout (re-login agar aktif)." \
    || echo "    [WARN] gagal menambah grup dialout (lewati bila sudah anggota)."

  # Tulis unit. GUI butuh sesi X aktif: pakai graphical.target + DISPLAY/XAUTHORITY.
  sudo tee "$SERVICE_FILE" >/dev/null <<UNIT
[Unit]
Description=RECELL-AI Battery Grading Dashboard
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${ROOT_DIR}/jetson/src
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${SERVICE_USER}/.Xauthority
ExecStart=${ROOT_DIR}/venv/bin/python ui_dashboard.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
UNIT

  sudo systemctl daemon-reload
  sudo systemctl enable recell.service \
    && echo "    + service di-enable (jalan otomatis di layar HDMI saat boot)." \
    || echo "    [WARN] gagal enable service — cek systemd & izin sudo."
fi

echo "============================================="
echo " SETUP OFFLINE SELESAI!"
echo
echo " Service 'recell' aktif saat boot ke desktop (graphical.target)."
echo " Agar GUI muncul otomatis: pastikan Jetson AUTO-LOGIN ke desktop."
echo "   (Settings → Users → Automatic Login, atau via systemd set-default graphical.target)"
echo
echo " Perintah service:"
echo "   sudo systemctl start  recell      # jalankan sekarang (butuh sesi desktop aktif)"
echo "   sudo systemctl status recell      # cek status"
echo "   journalctl -u recell -f           # lihat log realtime"
echo
echo " Menjalankan manual (tanpa service):"
echo "   source venv/bin/activate && cd jetson/src"
echo "   python ui_dashboard.py            # GUI penuh (perlu display/Remote Desktop)"
echo "   python ui_dashboard.py --sim      # tanpa STM32 (uji UI)"
echo "============================================="
