"""Tanda tangan keaslian passport baterai (anti-pemalsuan, OFFLINE).

Hanya memakai stdlib (`hmac`, `hashlib`, `secrets`) supaya bisa dipakai & diuji
tanpa dependency berat. Skema: bangun payload kanonik berurutan tetap dari hasil
uji, lalu HMAC-SHA256 dengan kunci rahasia per-alat. QR berisi `payload~sig`.
Verifikasi menghitung ulang HMAC dan membandingkan dengan `compare_digest`, jadi
mengubah satu field pun pada sertifikat akan membuat tanda tangan tidak cocok.
"""

import hmac
import hashlib
import secrets
from pathlib import Path

PAYLOAD_VERSION = "RC1"
_FIELD_ORDER = ["id", "grade", "soh", "v_drop", "internal_r", "date"]
_SEP = "~"  # pemisah payload<->signature (tak muncul di payload)


def _normalized(fields):
    """Format setiap field dengan presisi tetap supaya sign & verify reproducible."""
    return {
        "id":         str(fields["id"]),
        "grade":      str(fields["grade"]),
        "soh":        f"{float(fields['soh']):.1f}",
        "v_drop":     f"{float(fields['v_drop']):.3f}",
        "internal_r": f"{float(fields['internal_r']):.4f}",
        "date":       str(fields["date"]),
    }


def canonical_payload(fields):
    """String kanonik berurutan tetap: RC1|id|grade|soh|v_drop|internal_r|date."""
    f = _normalized(fields)
    return PAYLOAD_VERSION + "|" + "|".join(f[k] for k in _FIELD_ORDER)


def sign(fields, key):
    """HMAC-SHA256 hex dari payload kanonik dengan `key`."""
    msg = canonical_payload(fields).encode("utf-8")
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def build_qr_payload(fields, key):
    """String yang ditanam di QR: `<payload>~<signature>`."""
    return canonical_payload(fields) + _SEP + sign(fields, key)


def _parse_payload(payload):
    parts = payload.split("|")
    if len(parts) != 1 + len(_FIELD_ORDER) or parts[0] != PAYLOAD_VERSION:
        return None
    return dict(zip(_FIELD_ORDER, parts[1:]))


def verify(qr_string, key):
    """Verifikasi string QR. Return (ok, data).

    `ok` True hanya bila signature cocok DAN payload terformat benar. `data` berisi
    field terurai (untuk ditampilkan) meski signature gagal — agar verifier bisa
    menunjukkan isi yang diklaim sambil menandainya tidak sah.
    """
    try:
        payload, sig = qr_string.rsplit(_SEP, 1)
    except ValueError:
        return (False, {})

    data = _parse_payload(payload)
    if data is None:
        return (False, {})

    expected = hmac.new(key.encode("utf-8"), payload.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(expected, sig)
    return (ok, data)


def load_or_create_key(path):
    """Baca kunci rahasia dari `path`; bila tak ada, buat acak (64 hex) & persist.

    Kunci ini rahasia per-alat dan WAJIB di-gitignore. Auto-generate memastikan
    tiap unit punya kunci unik tanpa intervensi manual.
    """
    p = Path(path)
    if p.exists():
        existing = p.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    key = secrets.token_hex(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key, encoding="utf-8")
    try:
        p.chmod(0o600)  # batasi akses (best-effort; diabaikan di Windows)
    except Exception:
        pass
    print(f"[Passport] Kunci penandatangan baru dibuat di {p} "
          f"— RAHASIA: backup & jangan commit.")
    return key
