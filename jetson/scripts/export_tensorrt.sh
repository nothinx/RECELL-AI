#!/bin/bash
# Konversi best.pt -> best.engine (TensorRT) — JALANKAN DI JETSON.
# Engine bersifat spesifik GPU + versi JetPack/TensorRT mesin ini, jadi TIDAK bisa
# dibuat di PC lain. imgsz=320 & half=True dicocokkan dgn inferensi main.py (cepat).
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/jetson"

if [ -f "$ROOT_DIR/venv/bin/activate" ]; then
  source "$ROOT_DIR/venv/bin/activate"
fi

PT="models/weights/best.pt"
ENGINE="models/weights/best.engine"
[ -f "$PT" ] || { echo "[ERR] $PT tidak ada. git pull dulu."; exit 1; }

echo "[*] Export $PT -> TensorRT (imgsz=320, FP16). Ini bisa 5-15 menit di Jetson..."
yolo export model="$PT" format=engine device=0 half=True imgsz=320

if [ -f "$ENGINE" ]; then
  echo "[OK] $ENGINE dibuat. main.py akan otomatis memakainya (lebih dulu dari .pt)."
  echo "     Restart aplikasi: sudo systemctl restart recell"
else
  echo "[ERR] best.engine tidak terbentuk. Cek error di atas (biasanya onnx/onnxruntime-gpu"
  echo "      belum terinstall — lihat DEPLOY_GUIDE_RECELL.md Bagian 4)."
  exit 1
fi
