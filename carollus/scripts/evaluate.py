#!/usr/bin/env python3
"""
evaluate.py  —  RECELL-AI / Carollus
Membuat SEMUA visual presentasi computer vision dari model + dataset:

  1. results/confusion_matrix.png            (count)
  2. results/confusion_matrix_normalized.png (recall per kelas)
  3. results/per_class_metrics.png + .csv    (precision/recall/F1/akurasi)
  4. results/dataset_distribution.png        (jumlah gambar per kelas)
  5. results/sample_predictions.png          (grid contoh prediksi + confidence)
  6. results/training_curves.png             (loss/akurasi per epoch, jika results.csv ada)

Model yang dipakai: ONNX (ringan) bila ada, jika tidak coba .pt (ultralytics).

Cara pakai:
    python scripts/evaluate.py --data datasets/capture
    python scripts/evaluate.py --data datasets/capture --model models/best_cls.onnx --max-per-class 120
"""
import argparse
import csv
import random
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ----------------------------- Backend inferensi ----------------------------- #
class OnnxBackend:
    def __init__(self, model_path, classes, imgsz=224):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(model_path),
                                         providers=ort.get_available_providers())
        self.inp = self.sess.get_inputs()[0].name
        self.classes = classes
        self.imgsz = imgsz

    @staticmethod
    def _softmax(x):
        x = x - np.max(x); e = np.exp(x); return e / e.sum()

    def predict(self, img_bgr):
        img = cv2.resize(img_bgr, (self.imgsz, self.imgsz))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.ascontiguousarray(np.transpose(img, (2, 0, 1))[None])
        out = self.sess.run(None, {self.inp: blob})[0][0]
        probs = out if np.isclose(out.sum(), 1.0, atol=1e-3) else self._softmax(out)
        return int(np.argmax(probs)), float(np.max(probs))


class PtBackend:
    def __init__(self, model_path, imgsz=224):
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))
        self.classes = [self.model.names[i] for i in sorted(self.model.names)]
        self.imgsz = imgsz

    def predict(self, img_bgr):
        r = self.model.predict(img_bgr, imgsz=self.imgsz, verbose=False)[0]
        return int(r.probs.top1), float(r.probs.top1conf)


def load_classes(model_path):
    cfile = Path(model_path).parent / "classes.txt"
    if cfile.exists():
        return [l.strip() for l in cfile.read_text(encoding="utf-8").splitlines() if l.strip()]
    return None


def build_backend(model_path, imgsz):
    model_path = Path(model_path)
    if model_path.suffix == ".onnx":
        classes = load_classes(model_path) or ["KARAT", "KOSONG", "SEHAT", "SOBEK"]
        return OnnxBackend(model_path, classes, imgsz), classes
    be = PtBackend(model_path, imgsz)
    return be, be.classes


# ----------------------------- Pengumpulan data ----------------------------- #
def gather(data_dir, classes, max_per_class):
    """Kembalikan list (path, true_idx). Folder dataset = nama kelas."""
    data_dir = Path(data_dir)
    items = []
    counts = {c: 0 for c in classes}
    for ci, c in enumerate(classes):
        cdir = data_dir / c
        if not cdir.is_dir():
            print(f"[warn] folder kelas tidak ada: {cdir}")
            continue
        files = [f for f in sorted(cdir.iterdir()) if f.suffix.lower() in IMG_EXT]
        counts[c] = len(files)
        random.seed(42)
        random.shuffle(files)
        for f in files[:max_per_class]:
            items.append((f, ci))
    return items, counts


# ----------------------------- Plot helpers ----------------------------- #
def plot_confusion(cm, classes, out, normalize=False, title=""):
    M = cm.astype(float)
    if normalize:
        M = M / M.sum(axis=1, keepdims=True).clip(min=1)
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(M, cmap="Blues", vmin=0, vmax=M.max() if M.max() else 1)
    ax.set_xticks(range(len(classes))); ax.set_xticklabels(classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes))); ax.set_yticklabels(classes)
    ax.set_xlabel("Prediksi"); ax.set_ylabel("Aktual")
    ax.set_title(title or ("Confusion Matrix (normalized)" if normalize else "Confusion Matrix"))
    for i in range(len(classes)):
        for j in range(len(classes)):
            v = M[i, j]
            txt = f"{v:.2f}" if normalize else f"{int(cm[i, j])}"
            ax.text(j, i, txt, ha="center", va="center",
                    color="white" if v > M.max() * 0.6 else "black", fontsize=10)
    fig.colorbar(im, fraction=0.046, pad=0.04)
    fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)
    print(f"[OK] {out}")


def metrics_table(cm, classes, out_png, out_csv):
    cm = cm.astype(float)
    tp = np.diag(cm)
    support = cm.sum(axis=1)
    prec = tp / cm.sum(axis=0).clip(min=1)
    rec = tp / support.clip(min=1)
    f1 = 2 * prec * rec / (prec + rec).clip(min=1e-9)
    acc = tp.sum() / cm.sum()

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class", "precision", "recall", "f1", "support"])
        for i, c in enumerate(classes):
            w.writerow([c, f"{prec[i]:.4f}", f"{rec[i]:.4f}", f"{f1[i]:.4f}", int(support[i])])
        w.writerow(["ACCURACY", "", "", f"{acc:.4f}", int(cm.sum())])

    fig, ax = plt.subplots(figsize=(7.2, 0.6 * len(classes) + 1.8))
    ax.axis("off")
    rows = [[c, f"{prec[i]:.3f}", f"{rec[i]:.3f}", f"{f1[i]:.3f}", int(support[i])]
            for i, c in enumerate(classes)]
    rows.append(["Accuracy", "", "", f"{acc:.3f}", int(cm.sum())])
    tbl = ax.table(cellText=rows,
                   colLabels=["Kelas", "Precision", "Recall", "F1", "Support"],
                   loc="center", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(11); tbl.scale(1, 1.6)
    for j in range(5):
        tbl[0, j].set_facecolor("#2563eb"); tbl[0, j].set_text_props(color="white", weight="bold")
    ax.set_title("Metrik Per-Kelas", pad=14, fontsize=13, weight="bold")
    fig.tight_layout(); fig.savefig(out_png, dpi=150, bbox_inches="tight"); plt.close(fig)
    print(f"[OK] {out_png}  &  {out_csv}  | akurasi keseluruhan = {acc*100:.2f}%")
    return acc


def plot_distribution(counts, out):
    classes = list(counts.keys()); vals = list(counts.values())
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    bars = ax.bar(classes, vals, color=["#ef4444", "#9ca3af", "#22c55e", "#f59e0b"][:len(classes)])
    ax.set_ylabel("Jumlah gambar"); ax.set_title("Distribusi Dataset per Kelas")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + max(vals) * 0.01, str(v),
                ha="center", va="bottom", fontsize=10)
    fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)
    print(f"[OK] {out}")


def plot_samples(backend, items, classes, out, n=8):
    random.seed(7)
    sel = random.sample(items, min(n, len(items)))
    cols = 4; rows = (len(sel) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3, rows * 3))
    axes = np.array(axes).reshape(-1)
    for ax in axes:
        ax.axis("off")
    for ax, (path, true_i) in zip(axes, sel):
        img = cv2.imread(str(path))
        pred_i, conf = backend.predict(img)
        rgb = cv2.cvtColor(cv2.resize(img, (224, 224)), cv2.COLOR_BGR2RGB)
        ax.imshow(rgb)
        ok = (pred_i == true_i)
        ax.set_title(f"pred: {classes[pred_i]} {conf*100:.0f}%\nasli: {classes[true_i]}",
                     color="green" if ok else "red", fontsize=9)
    fig.suptitle("Contoh Prediksi Model", fontsize=13, weight="bold")
    fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)
    print(f"[OK] {out}")


def plot_training_curves(results_csv, out):
    if not Path(results_csv).exists():
        print(f"[skip] training_curves: {results_csv} tidak ada "
              f"(salin results.csv dari folder runs/ training Anda ke sini).")
        return
    import pandas as pd
    df = pd.read_csv(results_csv); df.columns = [c.strip() for c in df.columns]
    fig, ax1 = plt.subplots(figsize=(7, 4.4))
    loss_cols = [c for c in df.columns if "loss" in c.lower()]
    for c in loss_cols:
        ax1.plot(df["epoch"], df[c], label=c)
    ax1.set_xlabel("Epoch"); ax1.set_ylabel("Loss"); ax1.legend(loc="upper right", fontsize=8)
    acc_cols = [c for c in df.columns if "accuracy" in c.lower() or "top1" in c.lower()]
    if acc_cols:
        ax2 = ax1.twinx()
        for c in acc_cols:
            ax2.plot(df["epoch"], df[c], "--", color="green", label=c)
        ax2.set_ylabel("Accuracy"); ax2.legend(loc="lower right", fontsize=8)
    ax1.set_title("Kurva Training")
    fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)
    print(f"[OK] {out}")


# ----------------------------- Main ----------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="datasets/capture",
                    help="Folder dataset berisi subfolder per kelas")
    ap.add_argument("--model", default="models/best_cls.onnx")
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--max-per-class", type=int, default=120,
                    help="Batas gambar dievaluasi per kelas (cepat). 0 = semua")
    ap.add_argument("--results-csv", default="results/results.csv",
                    help="CSV log training ultralytics untuk kurva (opsional)")
    args = ap.parse_args()

    out_dir = Path("results"); out_dir.mkdir(exist_ok=True)

    model_path = Path(args.model)
    if not model_path.exists():
        alt = model_path.with_suffix(".pt")
        if alt.exists():
            print(f"[i] {model_path} tidak ada, memakai {alt}")
            model_path = alt
        else:
            raise SystemExit(f"[!] Model tidak ditemukan: {args.model}")

    backend, classes = build_backend(model_path, args.imgsz)
    print(f"[*] Backend: {model_path.name} | kelas: {classes}")

    mpc = args.max_per_class if args.max_per_class > 0 else 10 ** 9
    items, counts = gather(args.data, classes, mpc)
    if not items:
        raise SystemExit("[!] Tidak ada gambar terkumpul. Cek --data.")
    print(f"[*] Mengevaluasi {len(items)} gambar ...")

    cm = np.zeros((len(classes), len(classes)), dtype=int)
    for k, (path, true_i) in enumerate(items, 1):
        img = cv2.imread(str(path))
        if img is None:
            continue
        pred_i, _ = backend.predict(img)
        cm[true_i, pred_i] += 1
        if k % 100 == 0:
            print(f"    {k}/{len(items)}")

    plot_confusion(cm, classes, out_dir / "confusion_matrix.png", normalize=False)
    plot_confusion(cm, classes, out_dir / "confusion_matrix_normalized.png", normalize=True)
    metrics_table(cm, classes, out_dir / "per_class_metrics.png", out_dir / "per_class_metrics.csv")
    plot_distribution(counts, out_dir / "dataset_distribution.png")
    plot_samples(backend, items, classes, out_dir / "sample_predictions.png")
    plot_training_curves(args.results_csv, out_dir / "training_curves.png")
    print("\n[SELESAI] Semua visual tersimpan di folder results/")


if __name__ == "__main__":
    main()
