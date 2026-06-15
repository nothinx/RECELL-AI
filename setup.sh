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

# 5. Buat struktur folder data
echo "[*] Membuat folder data..."
mkdir -p jetson/data/passports
mkdir -p jetson/data/logs
mkdir -p jetson/models/weights
mkdir -p jetson/models/engines

# 6. Verifikasi CUDA torch
echo "[*] Verifikasi PyTorch + CUDA..."
python -c "import torch; print('torch', torch.__version__, '| CUDA tersedia:', torch.cuda.is_available())" || \
  echo "[WARN] Verifikasi torch gagal — cek wheel torch di wheelhouse cocok dgn JetPack/CUDA Jetson."

echo "============================================="
echo " SETUP OFFLINE SELESAI!"
echo " Menjalankan aplikasi:"
echo "   1. source venv/bin/activate"
echo "   2. cd jetson/src"
echo "   3. python ui_dashboard.py            # GUI penuh (perlu display/Remote Desktop)"
echo "      python ui_dashboard.py --sim      # tanpa STM32 (uji UI)"
echo "============================================="
