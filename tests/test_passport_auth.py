"""Test keaslian passport (stdlib, jalan di env mana pun tanpa reportlab/qrcode).

Gaya runner __main__ seperti tests/test_protocol_sync.py supaya bisa dijalankan
dengan `python tests/test_passport_auth.py` walau pytest tak terpasang.
"""
import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jetson" / "src"))
import passport_auth as pa  # noqa: E402

FIELDS = {
    "id": "RC-20260615-101500", "grade": "A", "soh": 87.4,
    "v_drop": 0.231, "internal_r": 0.1612, "date": "2026-06-15T10:15:00",
}
KEY = "testkey"


def test_sign_deterministic():
    s1 = pa.sign(FIELDS, KEY)
    s2 = pa.sign(FIELDS, KEY)
    assert s1 == s2
    assert len(s1) == 64
    assert all(c in "0123456789abcdef" for c in s1)


def test_verify_roundtrip():
    qr = pa.build_qr_payload(FIELDS, KEY)
    ok, data = pa.verify(qr, KEY)
    assert ok is True
    assert data["id"] == "RC-20260615-101500"
    assert data["grade"] == "A"
    assert float(data["soh"]) == 87.4


def test_tamper_detected():
    qr = pa.build_qr_payload(FIELDS, KEY)
    tampered = qr.replace("|A|", "|R|", 1)
    assert tampered != qr  # pastikan benar-benar berubah
    ok, _ = pa.verify(tampered, KEY)
    assert ok is False


def test_wrong_key():
    qr = pa.build_qr_payload(FIELDS, KEY)
    ok, _ = pa.verify(qr, "otherkey")
    assert ok is False


def test_load_or_create_key():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "sub", "passport_key.txt")
    k1 = pa.load_or_create_key(path)
    assert len(k1) == 64
    k2 = pa.load_or_create_key(path)  # baca ulang -> sama
    assert k1 == k2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("OK passport auth")
