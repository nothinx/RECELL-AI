#!/usr/bin/env bash
# RECELL-AI / Carollus — pipeline 1-klik (Linux/macOS/Git-Bash)
# Jalankan dari DALAM folder carollus/ :  bash run_all.sh
set -e
cd "$(dirname "$0")"

echo "=== [1/4] Install dependencies ==="
pip install -r requirements.txt

echo "=== [2/4] Konversi model .pt -> .onnx (ringan) ==="
python scripts/export_onnx.py --weights models/best_cls.pt --imgsz 224

echo "=== [3/4] Buat semua visual evaluasi (confusion matrix dll) ==="
# arahkan --data ke folder dataset Anda (subfolder per kelas)
python scripts/evaluate.py --data ../datasets/capture --model models/best_cls.onnx --max-per-class 120

echo "=== [4/4] Tes deploy pada 1 sample ==="
python scripts/deploy_onnx.py --source sample_images/SEHAT_sample.jpg

echo ""
echo "SELESAI. Lihat hasil visual di folder results/"
