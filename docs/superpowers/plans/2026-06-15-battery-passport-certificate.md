# Battery Passport Certificate — Implementation Plan

> **For agentic workers:** gunakan superpowers:subagent-driven-development atau executing-plans. Langkah pakai checkbox `- [ ]`.

**Goal:** Sertifikat baterai premium A5 PDF (offline) dengan foto, Unique ID `RC-...`, segel grade, data bilingual, sparkline discharge, dan QR ber-HMAC anti-pemalsuan.

**Architecture:** Tiga unit terpisah — `passport_auth.py` (stdlib: HMAC sign/verify, teruji penuh), `passport_generator.py` (render reportlab, dibungkus try/except), `verify_passport.py` (CLI). `main.py` mengintegrasikan ID baru + data kaya.

**Tech Stack:** Python, reportlab, qrcode, hmac/hashlib (stdlib).

---

## Task 1: `passport_auth.py` + test (TDD, stdlib)

**Files:** Create `jetson/src/passport_auth.py`, `tests/test_passport_auth.py`

- [ ] **Step 1: Tulis test gagal** `tests/test_passport_auth.py` (gaya `__main__` runner seperti `test_protocol_sync.py`):
  - import dari `jetson/src` via `sys.path`.
  - `FIELDS = {"id":"RC-20260615-101500","grade":"A","soh":87.4,"v_drop":0.231,"internal_r":0.1612,"date":"2026-06-15T10:15:00"}`, `KEY="testkey"`.
  - `test_sign_deterministic`: `sign(FIELDS,KEY)==sign(FIELDS,KEY)` dan panjang 64 hex.
  - `test_verify_roundtrip`: `qr=build_qr_payload(FIELDS,KEY)`; `ok,data=verify(qr,KEY)`; `ok is True`; `data["grade"]=="A"`, `float(data["soh"])==87.4`.
  - `test_tamper_detected`: ganti `|A|` jadi `|R|` di qr → `verify(...)[0] is False`.
  - `test_wrong_key`: `verify(qr,"otherkey")[0] is False`.
  - `test_load_or_create_key`: ke tmp path → buat file 64 hex; panggil dua kali → nilai sama.

- [ ] **Step 2: Jalankan, pastikan gagal** `python tests/test_passport_auth.py` → error import (modul belum ada).

- [ ] **Step 3: Implementasi `jetson/src/passport_auth.py`** (stdlib saja):
  - `PAYLOAD_VERSION="RC1"`, `_FIELD_ORDER=["id","grade","soh","v_drop","internal_r","date"]`, format angka tetap (`soh:.1f`,`v_drop:.3f`,`internal_r:.4f`).
  - `canonical_payload(fields)`: `"RC1|"+ "|".join(...)`.
  - `sign(fields,key)`: `hmac.new(key.encode(), canonical_payload(fields).encode(), hashlib.sha256).hexdigest()`.
  - `build_qr_payload(fields,key)`: `f"{canonical_payload(fields)}~{sign(fields,key)}"`.
  - `verify(qr,key)`: split `~` (rsplit, 1); recompute HMAC dari bagian payload; `hmac.compare_digest`; parse payload `RC1|id|grade|soh|v_drop|internal_r|date` → dict. Return `(False,{})` bila format salah.
  - `load_or_create_key(path)`: kalau ada → baca strip; else `secrets.token_hex(32)`, tulis, return.

- [ ] **Step 4: Jalankan test → semua PASS.** `python tests/test_passport_auth.py`.

- [ ] **Step 5: Commit** `git add jetson/src/passport_auth.py tests/test_passport_auth.py && git commit -m "feat(passport): HMAC-signed payload auth (stdlib) + tests"`

---

## Task 2: `passport_generator.py` (render reportlab A5)

**Files:** Rewrite `jetson/src/passport_generator.py`

- [ ] **Step 1: Implementasi** kelas `BatteryPassport` dengan `generate_pdf(self, battery_id, grade, vision_score, volt, curr, soh, image_path, measurement=None, defects=None, timestamp=None)`:
  - Bungkus seluruh body `try/except Exception` → log + `return None` (siklus tak boleh crash).
  - Lazy-import `reportlab` + `qrcode` di dalam fungsi; bila ImportError → log "passport deps missing" + return None.
  - Ukuran A5 (`from reportlab.lib.pagesizes import A5`), canvas ke `data/passports/Passport_<id>.pdf`.
  - Palet & helper gambar: guilloche border (loop garis Lissajous tipis emas), header wordmark (Times-Bold), garis emas.
  - Foto: `c.drawImage(image_path,...)` bila `os.path.exists`, else placeholder kotak "NO PHOTO · Tanpa Foto".
  - Segel grade: lingkaran warna grade + huruf besar (Times-Bold) + subtitle bilingual; SoH besar + bar mini.
  - Tabel data bilingual dari `measurement` (fallback ke volt/curr/soh) + vision_score + timestamp.
  - Sparkline: baca `data/logs/discharge_curve.csv`, filter `battery_id`, plot Voltage vs t_ms sebagai polyline kecil; lewati bila kosong/error.
  - QR: `fields` dari (id,grade,soh,v_drop,internal_r,date); `key=passport_auth.load_or_create_key(config/passport_key.txt)`; `qrstr=build_qr_payload(...)`; render matriks `qrcode.QRCode`→`get_matrix()` jadi kotak vektor; cetak 12 hex pertama sig (mono Courier).
  - Footer pernyataan bilingual. `c.save()`, return path.
  - Font: registrasi opsional TTF dari `jetson/assets/fonts/` bila ada; else pakai Times/Helvetica/Courier bawaan.

- [ ] **Step 2: Smoke (bila reportlab ada di mesin ini)** `python -c "import sys;sys.path.insert(0,'jetson/src');from passport_generator import BatteryPassport;p=BatteryPassport('/tmp/pp');print(p.generate_pdf('RC-20260615-101500','A',0.9,3.75,1.5,87.4,'',measurement={'v_drop':0.23,'internal_r':0.16,'v_resting':3.98,'v_loaded':3.75,'temp_delta':2.1,'current_load':1.5,'temp_pre':28.0,'temp_post':30.1},defects=[],timestamp='2026-06-15T10:15:00'))"` → cetak path PDF. Bila reportlab tak terpasang di mesin ini → catat SKIP (diverifikasi di Jetson).

- [ ] **Step 3: Commit** `git add jetson/src/passport_generator.py && git commit -m "feat(passport): premium A5 reportlab certificate with signed QR"`

---

## Task 3: CLI verifikasi + integrasi main.py + deps

**Files:** Create `jetson/scripts/verify_passport.py`; Modify `jetson/src/main.py`, `jetson/requirements-jetson-runtime.txt`, `.gitignore`

- [ ] **Step 1: `jetson/scripts/verify_passport.py`** — argparse 1 arg `qr`; `key=passport_auth.load_or_create_key(<config path>)`; `ok,data=verify(qr,key)`; cetak `VALID`/`INVALID` + data (exit 0/1). Sisipkan `sys.path` ke `../src`.

- [ ] **Step 2: main.py — ID baru.** Ganti `battery_id = f"BAT_{int(cycle_start)}"` → `battery_id = time.strftime("RC-%Y%m%d-%H%M%S")`.

- [ ] **Step 3: main.py — perkaya pemanggilan passport.** Ubah blok `pdf_path = self.passport_gen.generate_pdf(...)` agar mengoper `measurement=self.measurement_detail, defects=self.get_confirmed_defects(), timestamp=datetime...`. Tambah `from datetime import datetime` bila belum ada (atau pakai `time.strftime`).

- [ ] **Step 4: deps + gitignore.** Tambah baris `reportlab` & `qrcode` di `jetson/requirements-jetson-runtime.txt`. Tambah `jetson/config/passport_key.txt` ke `.gitignore`.

- [ ] **Step 5: Verifikasi tak ada regresi.** `python tests/test_protocol_sync.py` → hijau; `python tests/test_passport_auth.py` → hijau; `python -c "import ast;ast.parse(open('jetson/src/main.py').read());print('main OK')"`.

- [ ] **Step 6: Commit** `git add -A && git commit -m "feat(passport): verify CLI, readable RC-id, main.py integration, offline deps"`

---

## Self-Review (hasil)
- Spec §4 HMAC → Task 1 (teruji tamper/wrong-key). §3/§5 render → Task 2. §6 integrasi + §9 deps → Task 3.
- Tanpa placeholder; nama API konsisten (`canonical_payload/sign/build_qr_payload/verify/load_or_create_key`).
- Ketahanan §7 tercakup di Task 2 try/except + fallback. Test §8 di Task 1 & Step 5.
