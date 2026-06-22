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

# Preflight: TensorRT export & inferensi cepat butuh GPU. Wheel torch generik
# (mis. +cu130) tak cocok driver Jetson -> CUDA mati -> CPU only (lambat) & export gagal.
python - <<'PY' || exit 2
import sys, torch
if not torch.cuda.is_available():
    print(f"[ERR] PyTorch TIDAK melihat GPU (torch {torch.__version__}, cuda.is_available()=False).")
    print("      Wheel torch salah untuk Jetson. Perbaiki dulu:")
    print("        pip uninstall -y torch torchvision")
    print("        pip install torch torchvision --index-url https://pypi.jetson-ai-lab.io/jp6/cu126")
    print("      (sesuaikan jp6/cu126 dgn JetPack-mu; cek: cat /etc/nv_tegra_release)")
    print("      Verifikasi: python -c \"import torch;print(torch.cuda.is_available())\" -> True")
    sys.exit(2)
print(f"[OK] GPU aktif: {torch.cuda.get_device_name(0)} (torch {torch.__version__})")
PY

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
