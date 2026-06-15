#!/usr/bin/env python3
"""Verifikasi keaslian QR passport baterai RECELL-AI (OFFLINE).

Pakai:
    python verify_passport.py "<isi_string_QR>"

Membaca kunci rahasia dari jetson/config/passport_key.txt (kunci yang sama
dipakai saat sertifikat diterbitkan). Mencetak VALID/INVALID + data terurai.
Exit code 0 bila VALID, 1 bila INVALID — agar mudah dipakai di skrip.
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import passport_auth  # noqa: E402

KEY_PATH = Path(__file__).resolve().parent.parent / "config" / "passport_key.txt"


def main():
    ap = argparse.ArgumentParser(description="Verifikasi QR passport RECELL-AI")
    ap.add_argument("qr", help="Isi string QR (format: payload~signature)")
    args = ap.parse_args()

    key = passport_auth.load_or_create_key(str(KEY_PATH))
    ok, data = passport_auth.verify(args.qr, key)

    print("VALID" if ok else "INVALID")
    for k, v in data.items():
        print(f"  {k:11s}: {v}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
