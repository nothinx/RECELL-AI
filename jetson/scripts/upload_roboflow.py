#!/usr/bin/env python3
"""Upload folder gambar (hasil capture_dataset.py) ke Roboflow untuk dianotasi.

Setup sekali di mesin yang upload (Jetson/PC):
    pip install roboflow
    export ROBOFLOW_API_KEY=xxxxxxxx     # app.roboflow.com -> Settings -> Roboflow API -> Private API Key

Pakai:
    python3 jetson/scripts/upload_roboflow.py --workspace <WS> --project <PROJ> --folder datasets/capture

Buat project dulu di app.roboflow.com (type: Object Detection). <WS> & <PROJ>
adalah slug di URL project (app.roboflow.com/<WS>/<PROJ>). Setelah upload,
anotasi di web (kelas: KARAT, SEHAT, SOBEK), Generate version, Export YOLOv8.

ponytail: SDK resmi roboflow = CLI yang cukup; tak perlu node/npm-cli terpisah.
"""
import argparse
import os
import sys
from pathlib import Path

# File key lokal (gitignored) — supaya tak usah export tiap kali. Jangan commit.
KEY_FILE = Path(__file__).resolve().parents[1] / ".roboflow_key"   # jetson/.roboflow_key


def _key():
    return os.environ.get("ROBOFLOW_API_KEY") or (
        KEY_FILE.read_text().strip() if KEY_FILE.exists() else None)


def main():
    ap = argparse.ArgumentParser(description="Upload gambar ke Roboflow.")
    ap.add_argument("--workspace", required=True, help="slug workspace Roboflow")
    ap.add_argument("--project", required=True, help="slug project Roboflow")
    ap.add_argument("--folder", default="datasets/capture", help="folder berisi *.jpg")
    ap.add_argument("--api-key", default=_key(),
                    help="default dari env ROBOFLOW_API_KEY atau jetson/.roboflow_key")
    ap.add_argument("--split", default="train", choices=["train", "valid", "test"])
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("[!] Tak ada API key. Set env ROBOFLOW_API_KEY atau --api-key.")
    try:
        from roboflow import Roboflow
    except ImportError:
        sys.exit("[!] Paket belum ada: pip install roboflow")

    imgs = sorted(Path(args.folder).glob("*.jpg"))
    if not imgs:
        sys.exit(f"[!] Tak ada .jpg di {args.folder}")

    project = Roboflow(api_key=args.api_key).workspace(args.workspace).project(args.project)
    print(f"[upload] {len(imgs)} gambar -> {args.workspace}/{args.project} (split={args.split})")
    ok = 0
    for i, p in enumerate(imgs, 1):
        try:
            project.upload(str(p), split=args.split)
            ok += 1
            print(f"  [{i}/{len(imgs)}] {p.name}")
        except Exception as e:                       # 1 gambar gagal jangan gagalkan semua
            print(f"  [{i}/{len(imgs)}] GAGAL {p.name}: {e}")
    print(f"[upload] selesai: {ok}/{len(imgs)} sukses. Anotasi di app.roboflow.com.")


if __name__ == "__main__":
    main()
