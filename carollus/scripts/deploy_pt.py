#!/usr/bin/env python3
"""
deploy_pt.py  —  RECELL-AI / Carollus
Inferensi memakai model PyTorch asli (best_cls.pt) via ultralytics.

Gunakan ini untuk verifikasi/validasi (lebih berat: butuh torch + ultralytics).
Untuk deploy ringan, pakai deploy_onnx.py.

Cara pakai:
    python scripts/deploy_pt.py --source sample_images/KARAT_sample.jpg
    python scripts/deploy_pt.py --source datasets/capture/SEHAT
    python scripts/deploy_pt.py --source 0 --show      # webcam
"""
import argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="models/best_cls.pt")
    ap.add_argument("--source", default="sample_images/SEHAT_sample.jpg")
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("[!] Pasang dulu: pip install -r requirements.txt")

    model = YOLO(args.weights)
    print(f"[*] Kelas: {model.names}\n")

    results = model.predict(source=args.source, imgsz=args.imgsz,
                            show=args.show, stream=False, verbose=False)
    for r in results:
        top1 = int(r.probs.top1)
        conf = float(r.probs.top1conf)
        name = model.names[top1]
        src = Path(r.path).name if r.path else "frame"
        print(f"{src:40s} -> {name:7s} {conf*100:5.1f}%")


if __name__ == "__main__":
    main()
