#!/bin/bash
# ============================================================================
#  RECELL-AI — SETUP Jetson Orin Nano Super
# ----------------------------------------------------------------------------
#  Mode:
#    bash setup.sh              → OFFLINE (dari wheelhouse/, tanpa internet)
#    bash setup.sh --online     → ONLINE  (pip install langsung dari internet)
#
#  Flag tambahan:
#    --no-service               → lewati pemasangan systemd service
# ============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHEELHOUSE="$ROOT_DIR/wheelhouse"
ONLINE=false
NO_SERVICE=false

for arg in "$@"; do
  case "$arg" in
    --online)     ONLINE=true ;;
    --no-service) NO_SERVICE=true ;;
  esac
done

if $ONLINE; then
  echo "============================================="
  echo " RECELL-AI ONLINE SETUP (Jetson, ada internet)"
  echo "============================================="
else
  echo "============================================="
  echo " RECELL-AI OFFLINE SETUP (Jetson, air-gapped)"
  echo "============================================="
fi

# 0. Sanity check (offline: perlu wheelhouse; online: perlu internet)
if ! $ONLINE; then
  if [ ! -d "$WHEELHOUSE" ]; then
    echo "[FATAL] Folder wheelhouse/ tidak ditemukan di $ROOT_DIR"
    echo "        Gunakan --online bila Jetson ada internet, atau transfer wheelhouse/ dulu."
    exit 1
  fi
fi

# 1. Virtual environment dengan akses paket sistem JetPack (PyQt5 + OpenCV CUDA)
echo "[*] Membuat virtual environment (--system-site-packages)..."
python3 -m venv --system-site-packages venv
source venv/bin/activate

# 2. Install torch & torchvision (build CUDA Jetson)
echo "[*] Install torch & torchvision (CUDA Jetson)..."
if $ONLINE; then
  pip install torch torchvision \
    --extra-index-url https://pypi.jetson-ai-lab.dev/jp6/cu126
else
  if ls "$WHEELHOUSE"/pip-*.whl >/dev/null 2>&1; then
    pip install --no-index --find-links="$WHEELHOUSE" --upgrade pip
  fi
  pip install --no-index --find-links="$WHEELHOUSE" torch torchvision
fi

# 3. Install dependency runtime
echo "[*] Install dependency runtime..."
if $ONLINE; then
  pip install -r jetson/requirements-jetson-runtime.txt
else
  pip install --no-index --find-links="$WHEELHOUSE" -r jetson/requirements-jetson-runtime.txt
fi

# 4. Matikan ultralytics telemetry (persists ke ~/.config/Ultralytics/settings.yaml)
echo "[*] Matikan ultralytics telemetry..."
python -c "from ultralytics import settings; settings.update({'sync': False})" || \
  echo "    [WARN] Gagal matikan telemetry — akan dicoba ulang saat runtime."

# 5. Pre-install ONNX export deps (untuk 'yolo export format=engine')
echo "[*] Install ONNX export deps (untuk konversi TensorRT)..."
if $ONLINE; then
  pip install onnx "onnxslim>=0.1.5" onnxruntime-gpu \
    --extra-index-url https://pypi.jetson-ai-lab.dev/jp6/cu126 2>/dev/null && \
    echo "    + onnx, onnxslim, onnxruntime-gpu terinstall." || \
    echo "    [INFO] onnxruntime-gpu tidak tersedia — onnx & onnxslim saja (cukup untuk export)."
else
  pip install --no-index --find-links="$WHEELHOUSE" onnx onnxslim 2>/dev/null && \
    echo "    + onnx, onnxslim terinstall." || \
    echo "    [INFO] onnx/onnxslim tidak ada di wheelhouse — tambahkan bila ingin konversi TensorRT offline."
fi

# 6. Buat struktur folder data
echo "[*] Membuat folder data..."
mkdir -p jetson/data/passports
mkdir -p jetson/data/logs
mkdir -p jetson/models/weights
mkdir -p jetson/models/engines

# 7. Verifikasi CUDA torch
echo "[*] Verifikasi PyTorch + CUDA..."
python -c "import torch; print('torch', torch.__version__, '| CUDA tersedia:', torch.cuda.is_available())" || \
  echo "[WARN] Verifikasi torch gagal — pastikan wheel torch adalah build CUDA Jetson."

deactivate 2>/dev/null || true

# 8. Service systemd autostart (GUI di monitor HDMI Jetson)
if $NO_SERVICE; then
  echo "[*] --no-service: lewati pemasangan systemd service."
else
  echo "[*] Memasang systemd service 'recell' (GUI autostart saat boot)..."
  SERVICE_USER="$(id -un)"
  SERVICE_FILE="/etc/systemd/system/recell.service"

  sudo usermod -aG dialout "$SERVICE_USER" 2>/dev/null \
    && echo "    + $SERVICE_USER ditambahkan ke grup dialout (re-login agar aktif)." \
    || echo "    [WARN] gagal menambah grup dialout (lewati bila sudah anggota)."

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
if $ONLINE; then
  echo " SETUP ONLINE SELESAI!"
else
  echo " SETUP OFFLINE SELESAI!"
fi
echo
echo " Service 'recell' aktif saat boot ke desktop (graphical.target)."
echo " Agar GUI muncul otomatis: pastikan Jetson AUTO-LOGIN ke desktop."
echo "   (Settings → Users → Automatic Login)"
echo
echo " Perintah service:"
echo "   sudo systemctl start  recell      # jalankan sekarang"
echo "   sudo systemctl status recell      # cek status"
echo "   journalctl -u recell -f           # log realtime"
echo
echo " Menjalankan manual:"
echo "   source venv/bin/activate && cd jetson/src"
echo "   python ui_dashboard.py            # GUI penuh"
echo "   python ui_dashboard.py --sim      # tanpa STM32"
echo "============================================="
