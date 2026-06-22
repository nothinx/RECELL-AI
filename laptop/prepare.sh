#!/bin/bash
# ============================================================================
#  RECELL-AI — PERSIAPAN WHEELHOUSE DI LAPTOP (saat ONLINE)
# ----------------------------------------------------------------------------
#  Jalankan skrip ini DI LAPTOP (Windows Git Bash / Linux / macOS) saat
#  laptop terhubung internet, SEBELUM transfer ke Jetson.
#
#  Output: folder wheelhouse/ berisi semua wheel aarch64/cp310 yang dibutuhkan
#  Jetson untuk install offline.
#
#  TIDAK perlu dijalankan ulang kecuali menambah/mengganti dependency.
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
WHEELHOUSE="$ROOT_DIR/wheelhouse"
RUNTIME_REQS="$ROOT_DIR/jetson/requirements-jetson-runtime.txt"

echo "============================================="
echo " RECELL-AI — Persiapan Wheelhouse (LAPTOP)"
echo " Target folder: $WHEELHOUSE"
echo "============================================="

# Pastikan requirements file ada
if [ ! -f "$RUNTIME_REQS" ]; then
  echo "[FATAL] $RUNTIME_REQS tidak ditemukan. Jalankan dari root proyek RECELL-AI."
  exit 1
fi

mkdir -p "$WHEELHOUSE"

# 1. Unduh wheel runtime aarch64/cp310 dari PyPI
echo ""
echo "[1/3] Mengunduh wheel runtime (aarch64, Python 3.10) dari PyPI..."
echo "      Paket: ultralytics, xgboost, pandas, numpy, pyqtgraph, pyserial,"
echo "             reportlab, qrcode, Pillow"
echo "      (PyQt5 & opencv dilewati — pakai sistem JetPack via --system-site-packages)"
pip download \
  --only-binary=:all: \
  --platform manylinux2014_aarch64 \
  --python-version 310 --implementation cp --abi cp310 \
  -d "$WHEELHOUSE" \
  -r "$RUNTIME_REQS"

# 2. Unduh ONNX export deps (opsional — hanya dibutuhkan untuk 'yolo export format=engine')
#    onnx & onnxslim: ada di PyPI dengan wheel aarch64.
#    Tanpa ini, ultralytics mencoba pip install dari internet saat pertama kali export.
echo ""
echo "[2/3] Mengunduh ONNX export deps (untuk konversi TensorRT offline)..."
pip download \
  --only-binary=:all: \
  --platform manylinux2014_aarch64 \
  --python-version 310 --implementation cp --abi cp310 \
  -d "$WHEELHOUSE" \
  onnx "onnxslim>=0.1.5" 2>/dev/null && echo "      + onnx, onnxslim diunduh." || \
  echo "      [WARN] onnx/onnxslim gagal diunduh — konversi TensorRT perlu internet saat pertama kali."

# 3. Peringatan: torch, torchvision, onnxruntime-gpu harus diunduh MANUAL
echo ""
echo "[3/3] ============================================================"
echo "  PERLU UNDUH MANUAL ke folder wheelhouse/:"
echo ""
echo "  torch + torchvision + onnxruntime-gpu (build CUDA Jetson):"
echo "  → Buka di browser: https://pypi.jetson-ai-lab.io/jp6/cu126"
echo "  → Unduh file .whl untuk:"
echo "      torch          (pilih cp310 / aarch64)"
echo "      torchvision    (pilih cp310 / aarch64)"
echo "      onnxruntime-gpu (pilih cp310 / aarch64) — jika ingin export TensorRT"
echo "  → Simpan ke folder: $WHEELHOUSE"
echo "=================================================================="

# 4. Verifikasi isi wheelhouse
echo ""
echo "[Verifikasi] Cek wheel penting di wheelhouse:"
MISSING=0
for pkg in torch torchvision ultralytics opencv; do
  if ls "$WHEELHOUSE"/*${pkg}*.whl >/dev/null 2>&1; then
    echo "  [OK] $pkg"
  else
    echo "  [MISSING] $pkg — unduh manual (lihat [3/3] di atas)"
    MISSING=1
  fi
done
for pkg in xgboost pandas numpy PyQt5 pyserial; do
  if ls "$WHEELHOUSE"/*${pkg}*.whl >/dev/null 2>&1 || \
     ls "$WHEELHOUSE"/${pkg}*.whl >/dev/null 2>&1 || \
     ls "$WHEELHOUSE"/$(echo $pkg | tr '[:upper:]' '[:lower:]')*.whl >/dev/null 2>&1; then
    echo "  [OK] $pkg"
  else
    echo "  [WARN] $pkg tidak ditemukan (mungkin nama file berbeda — cek ls wheelhouse/)"
  fi
done

echo ""
if [ $MISSING -eq 1 ]; then
  echo "[!] Ada wheel yang belum ada. Unduh manual dulu sebelum transfer ke Jetson."
else
  echo "[OK] Wheelhouse siap. Lanjut transfer ke Jetson:"
  echo "     bash deploy/deploy.sh"
  echo "     # atau manual: scp -r RECELL-AI/ <user>@<ip_jetson>:~/"
fi
echo "============================================="
