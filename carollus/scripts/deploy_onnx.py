#!/usr/bin/env python3
"""
deploy_onnx.py  —  RECELL-AI / Carollus
Inferensi klasifikasi kondisi baterai 18650 memakai model ONNX.

Keunggulan: HANYA butuh onnxruntime + opencv + numpy (TANPA PyTorch/ultralytics),
sehingga ringan saat di-clone dan cepat di edge device.

Kelas (urut indeks):
    0 = KARAT   (terdapat karat di kutub)        -> defect
    1 = KOSONG  (tidak ada baterai / slot kosong) -> gate, abaikan
    2 = SEHAT   (baterai bersih & mulus)          -> kandidat Grade A
    3 = SOBEK   (wrapper/plastik terkelupas)       -> defect

Cara pakai:
    # 1 gambar:
    python scripts/deploy_onnx.py --source sample_images/SEHAT_sample.jpg

    # 1 folder gambar:
    python scripts/deploy_onnx.py --source datasets/capture/KARAT

    # webcam realtime (tekan q untuk keluar):
    python scripts/deploy_onnx.py --source 0 --show
"""
import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_classes(model_path: Path):
    """Ambil nama kelas dari classes.txt di samping model, atau pakai default."""
    cfile = model_path.parent / "classes.txt"
    if cfile.exists():
        return [l.strip() for l in cfile.read_text(encoding="utf-8").splitlines() if l.strip()]
    return ["KARAT", "KOSONG", "SEHAT", "SOBEK"]


def softmax(x):
    x = x - np.max(x)
    e = np.exp(x)
    return e / e.sum()


def preprocess(img_bgr, size=224):
    """Resize -> RGB -> [0,1] -> CHW -> batch. Sesuai pipeline YOLOv8-cls."""
    img = cv2.resize(img_bgr, (size, size), interpolation=cv2.INTER_LINEAR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))[None, ...]  # 1x3xHxW
    return np.ascontiguousarray(img)


def predict(session, input_name, img_bgr, classes, size=224):
    blob = preprocess(img_bgr, size)
    out = session.run(None, {input_name: blob})[0][0]
    probs = softmax(out) if not np.isclose(out.sum(), 1.0, atol=1e-3) else out
    idx = int(np.argmax(probs))
    return classes[idx], float(probs[idx]), probs


def iter_sources(source):
    p = Path(source)
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in IMG_EXT:
                yield str(f)
    else:
        yield str(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/best_cls.onnx", help="Path model ONNX")
    ap.add_argument("--source", default="sample_images/SEHAT_sample.jpg",
                    help="Gambar, folder, atau '0' untuk webcam")
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--show", action="store_true", help="Tampilkan jendela hasil")
    args = ap.parse_args()

    mpath = Path(args.model)
    if not mpath.exists():
        raise SystemExit(f"[!] Model ONNX tidak ada: {mpath}\n"
                         f"    Buat dulu dengan: python scripts/export_onnx.py")

    classes = load_classes(mpath)
    providers = ort.get_available_providers()  # CUDA dipakai otomatis jika ada
    sess = ort.InferenceSession(str(mpath), providers=providers)
    inp = sess.get_inputs()[0].name
    print(f"[*] Model : {mpath.name}  | providers: {providers}")
    print(f"[*] Kelas : {classes}\n")

    # ---- Mode webcam ----
    if args.source == "0" or args.source.isdigit():
        cap = cv2.VideoCapture(int(args.source))
        if not cap.isOpened():
            raise SystemExit("[!] Kamera tidak terbuka.")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t0 = time.time()
            label, conf, _ = predict(sess, inp, frame, classes, args.imgsz)
            fps = 1.0 / max(time.time() - t0, 1e-6)
            txt = f"{label} {conf*100:.1f}%  ({fps:.0f} FPS)"
            color = (0, 200, 0) if label == "SEHAT" else (0, 165, 255)
            cv2.putText(frame, txt, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            cv2.imshow("RECELL-AI Carollus", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        cap.release()
        cv2.destroyAllWindows()
        return

    # ---- Mode gambar / folder ----
    for path in iter_sources(args.source):
        img = cv2.imread(path)
        if img is None:
            print(f"[skip] gagal baca {path}")
            continue
        t0 = time.time()
        label, conf, probs = predict(sess, inp, img, classes, args.imgsz)
        ms = (time.time() - t0) * 1000
        dist = "  ".join(f"{c}:{p*100:4.1f}%" for c, p in zip(classes, probs))
        print(f"{Path(path).name:40s} -> {label:7s} {conf*100:5.1f}%  [{ms:5.1f} ms]  | {dist}")
        if args.show:
            cv2.putText(img, f"{label} {conf*100:.1f}%", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0), 2)
            cv2.imshow("hasil", img)
            cv2.waitKey(0)
    if args.show:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
