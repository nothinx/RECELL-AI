#!/usr/bin/env python3
"""Ambil gambar dataset dari kamera rig — setelan IDENTIK dengan app produksi
(848x480, MJPG, fokus terkunci) supaya dataset cocok domain inferensi.

Roboflow meng-anotasi gambar MENTAH (tanpa label), jadi script ini hanya
menyimpan JPG bernomor — anotasi dilakukan di Roboflow web setelah upload.

PENTING: service `recell` memegang /dev/video0. Hentikan dulu:
    sudo systemctl stop recell
    python3 jetson/scripts/capture_dataset.py --interval 0.7 --out datasets/capture
    sudo systemctl start recell

Mode default: auto-interval (headless, jalan via SSH). Letakkan baterai,
biarkan menjepret beberapa frame, geser/putar, ulangi. Ctrl+C untuk berhenti.
Pakai --preview hanya bila ada layar (jendela live + SPACE simpan, q keluar).

ponytail: standalone & cv2-only — tak impor main.py (hindari load torch/ultralytics).
"""
import argparse
import subprocess
import time
from datetime import datetime
from pathlib import Path

import cv2

CAM_WIDTH, CAM_HEIGHT, CAM_FOCUS = 848, 480, 115  # mirror jetson/src/main.py


def open_camera(index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise SystemExit(f"[!] Kamera index {index} gagal dibuka (service recell masih jalan?).")
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    return cap


def lock_focus(index):
    dev = f"/dev/video{index}"
    for ctrl in ("focus_automatic_continuous=0", f"focus_absolute={CAM_FOCUS}"):
        subprocess.run(["v4l2-ctl", "-d", dev, "-c", ctrl],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def save(frame, out_dir, n):
    name = out_dir / f"cap_{datetime.now():%Y%m%d-%H%M%S}-{n:04d}.jpg"
    cv2.imwrite(str(name), frame)
    return name


def main():
    ap = argparse.ArgumentParser(description="Capture dataset gambar dari kamera rig.")
    ap.add_argument("--out", default="datasets/capture", help="folder tujuan JPG")
    ap.add_argument("--index", type=int, default=0, help="indeks /dev/videoN")
    ap.add_argument("--interval", type=float, default=0.7, help="detik antar-frame (mode auto)")
    ap.add_argument("--max", type=int, default=0, help="berhenti setelah N frame (0=tak terbatas)")
    ap.add_argument("--preview", action="store_true", help="jendela live + SPACE simpan/q keluar (butuh layar)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = open_camera(args.index)
    # Fokus baru nempel setelah streaming jalan — ambil 1 frame dulu lalu kunci.
    cap.read(); time.sleep(0.3); lock_focus(args.index)

    n = sum(1 for _ in out_dir.glob("*.jpg"))  # lanjut dari yang sudah ada
    print(f"[capture] mulai. tersimpan ke {out_dir} (sudah ada {n}). Ctrl+C untuk stop.")
    try:
        if args.preview:
            while True:
                ok, frame = cap.read()
                if not ok:
                    continue
                cv2.imshow("RECELL capture (SPACE=simpan, q=keluar)", frame)
                k = cv2.waitKey(1) & 0xFF
                if k == ord(" "):
                    n += 1; print(f"  simpan #{n}: {save(frame, out_dir, n).name}")
                elif k == ord("q"):
                    break
        else:
            last = 0.0
            while True:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05); continue
                now = time.time()
                if now - last >= args.interval:
                    last = now
                    n += 1
                    print(f"  #{n}: {save(frame, out_dir, n).name}")
                    if args.max and n >= args.max:
                        break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"[capture] selesai. total {n} gambar di {out_dir}")


if __name__ == "__main__":
    main()
