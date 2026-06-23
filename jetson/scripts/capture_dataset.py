#!/usr/bin/env python3
"""Ambil gambar dataset dari kamera rig — setelan IDENTIK dengan app produksi
(848x480, MJPG, fokus terkunci) supaya dataset cocok domain inferensi.

Roboflow meng-anotasi gambar MENTAH (tanpa label), jadi script ini hanya
menyimpan JPG bernomor — anotasi dilakukan di Roboflow web setelah upload.

PENTING: service `recell` memegang /dev/video0. Hentikan dulu:
    sudo systemctl stop recell
    python3 jetson/scripts/capture_dataset.py --burst 8
    sudo systemctl start recell

MODE (default = BURST per-picu, cocok untuk ubah posisi/baterai tiap kali):
  default  : tekan ENTER -> ambil <burst> gambar sekaligus; geser baterai; ENTER lagi.
             ketik q + ENTER untuk keluar. Jalan via SSH (tanpa layar).
  --auto    : ambil terus tiap <interval> detik (tanpa picu).
  --preview : jendela live (butuh layar); SPACE = ambil <burst>, q = keluar.

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


def grab_burst(cap, out_dir, n, count, delay):
    """Ambil `count` frame berturut (jeda `delay` agar frame segar). Return total baru."""
    cap.read()  # flush 1 frame basi (kamera diam saat nunggu picu)
    for _ in range(count):
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        n += 1
        print(f"    #{n}: {save(frame, out_dir, n).name}")
        time.sleep(delay)
    return n


def main():
    ap = argparse.ArgumentParser(description="Capture dataset gambar dari kamera rig.")
    ap.add_argument("--out", default="datasets/capture", help="folder tujuan JPG")
    ap.add_argument("--index", type=int, default=0, help="indeks /dev/videoN")
    ap.add_argument("--burst", type=int, default=8, help="jumlah gambar per picu (ENTER/SPACE)")
    ap.add_argument("--burst-delay", type=float, default=0.15, help="detik antar-frame dalam satu burst")
    ap.add_argument("--auto", action="store_true", help="mode interval otomatis (tanpa picu)")
    ap.add_argument("--interval", type=float, default=0.7, help="detik antar-frame mode --auto")
    ap.add_argument("--max", type=int, default=0, help="berhenti setelah N frame (0=tak terbatas)")
    ap.add_argument("--preview", action="store_true", help="jendela live (butuh layar); SPACE=burst, q=keluar")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = open_camera(args.index)
    cap.read(); time.sleep(0.3); lock_focus(args.index)  # fokus nempel setelah stream jalan

    n = sum(1 for _ in out_dir.glob("*.jpg"))  # lanjut dari yang sudah ada
    print(f"[capture] ke {out_dir} (sudah ada {n}).")
    try:
        if args.preview:
            print("  jendela: SPACE = ambil burst, q = keluar.")
            while True:
                ok, frame = cap.read()
                if not ok:
                    continue
                cv2.imshow(f"RECELL capture (SPACE=ambil {args.burst}, q=keluar)", frame)
                k = cv2.waitKey(1) & 0xFF
                if k == ord(" "):
                    n = grab_burst(cap, out_dir, n, args.burst, args.burst_delay)
                elif k == ord("q"):
                    break
        elif args.auto:
            print(f"  mode AUTO: tiap {args.interval}s. Ctrl+C untuk stop.")
            last = 0.0
            while True:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05); continue
                if time.time() - last >= args.interval:
                    last = time.time()
                    n += 1
                    print(f"    #{n}: {save(frame, out_dir, n).name}")
                    if args.max and n >= args.max:
                        break
        else:
            print(f"  mode BURST: ENTER = ambil {args.burst} gambar, lalu geser baterai. q+ENTER = keluar.")
            while True:
                cmd = input(f"[{n} tersimpan] ENTER ambil {args.burst} / 'q' keluar > ").strip().lower()
                if cmd == "q":
                    break
                n = grab_burst(cap, out_dir, n, args.burst, args.burst_delay)
                if args.max and n >= args.max:
                    print(f"  capai --max {args.max}."); break
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"[capture] selesai. total {n} gambar di {out_dir}")


if __name__ == "__main__":
    main()
