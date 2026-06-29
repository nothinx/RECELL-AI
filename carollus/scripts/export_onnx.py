#!/usr/bin/env python3
"""
export_onnx.py  —  RECELL-AI / Carollus
Konversi model YOLOv8n-cls (best_cls.pt) ke format ONNX agar ringan & portabel.

ONNX (Open Neural Network Exchange) membuat model bisa dijalankan TANPA PyTorch,
cukup pakai onnxruntime (jauh lebih kecil). Cocok untuk di-clone & deploy.

Cara pakai:
    python scripts/export_onnx.py
    python scripts/export_onnx.py --weights models/best_cls.pt --imgsz 224 --opset 12

Hasil: models/best_cls.onnx
"""
import argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Export YOLOv8-cls .pt -> .onnx")
    ap.add_argument("--weights", default="models/best_cls.pt",
                    help="Path ke file .pt (default: models/best_cls.pt)")
    ap.add_argument("--imgsz", type=int, default=224,
                    help="Ukuran input training (classifier ini dilatih di 224)")
    ap.add_argument("--opset", type=int, default=12, help="Versi ONNX opset")
    ap.add_argument("--simplify", action="store_true",
                    help="Sederhanakan graph (butuh paket onnxslim/onnxsim)")
    args = ap.parse_args()

    w = Path(args.weights)
    if not w.exists():
        raise SystemExit(f"[!] Tidak menemukan {w}. Jalankan dari folder carollus/.")

    # Import di dalam fungsi supaya error-nya jelas kalau ultralytics belum dipasang
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit(
            "[!] ultralytics belum terpasang.\n"
            "    Jalankan dulu:  pip install -r requirements.txt"
        )

    print(f"[*] Memuat model: {w}")
    model = YOLO(str(w))

    print(f"[*] Mengekspor ke ONNX (imgsz={args.imgsz}, opset={args.opset}) ...")
    out = model.export(
        format="onnx",
        imgsz=args.imgsz,
        opset=args.opset,
        simplify=args.simplify,
        dynamic=False,
    )
    print(f"\n[OK] Model ONNX tersimpan di: {out}")
    print("     Sekarang Anda bisa deploy memakai scripts/deploy_onnx.py (tanpa PyTorch).")

    # Simpan daftar nama kelas agar deploy_onnx.py tidak perlu PyTorch lagi
    names = model.names  # dict {0:'KARAT', ...}
    classes_txt = w.parent / "classes.txt"
    with open(classes_txt, "w", encoding="utf-8") as f:
        for i in sorted(names):
            f.write(f"{names[i]}\n")
    print(f"[OK] Daftar kelas tersimpan di: {classes_txt}")


if __name__ == "__main__":
    main()
