# Spec — Battery Passport Certificate (Premium, Anti-Counterfeit, Offline)

**Tanggal:** 2026-06-15
**Status:** Disetujui untuk perencanaan
**File terdampak:** `jetson/src/passport_auth.py` (baru), `jetson/src/passport_generator.py` (tulis ulang),
`jetson/scripts/verify_passport.py` (baru), `jetson/src/main.py`, `tests/test_passport_auth.py` (baru),
`jetson/requirements-jetson-runtime.txt`, `.gitignore`, `jetson/assets/fonts/` (opsional).

---

## 1. Tujuan

Mengganti passport PDF generik berbasis FPDF dengan **sertifikat baterai premium** bergaya
passport/sertifikat resmi: foto baterai, **Unique ID**, grade sebagai segel, data teknis bilingual,
**QR bertanda tangan (anti-pemalsuan)** — seluruhnya berjalan **offline** di Jetson air-gapped.

## 2. Keputusan desain (final)

| Aspek | Keputusan |
|---|---|
| Tema | Sertifikat premium / passport resmi (guilloche emas, segel grade, palet cream) |
| Ukuran | **A5 potret, 1 halaman PDF** (muat 2-up di A4) |
| Renderer | **reportlab** (vektor, pure-Python, offline) menggantikan FPDF |
| QR | **vektor** dari matriks `qrcode` (tanpa Pillow) |
| Isi QR | Payload ringkas + **HMAC-SHA256** (anti-pemalsuan, offline) |
| Bahasa | **Bilingual** (label EN / ID) |
| Unique ID | **`RC-YYYYMMDD-HHMMSS`** (terbaca, unik per siklus) |
| Kurva discharge | **Sparkline kecil** dari `discharge_curve.csv` (dilewati rapi bila tak ada) |
| Font | Bawaan reportlab (Times serif + Helvetica + Courier mono); hook opsional TTF di `jetson/assets/fonts/` |

## 3. Palet & tata letak

**Palet:** kertas cream `#F7F3E8`, tinta charcoal `#1A1A2E`, aksen emas `#B08D3E`;
grade A=emerald `#10B981`, B=amber `#F59E0B`, R=merah `#EF4444`.

**Layout A5 potret (148×210mm):**
- Bingkai **guilloche** tipis emas mengelilingi halaman (kurva Lissajous/spirograph digambar segmen garis).
- **Header:** wordmark `RECELL-AI` (serif, spasi-huruf lebar) + tagline "DIGITAL BATTERY PASSPORT ·
  Paspor Baterai Digital" + garis emas tipis.
- **Kiri:** foto baterai berbingkai sudut emas; di bawah → Unique ID (mono) + chip defect (atau "No defects · Tanpa Cacat").
- **Kanan:** **segel grade** lingkaran (A/B/R, warna grade, teks arc "SECOND-LIFE COMPATIBLE" dll) +
  **SoH** angka besar + bar mini.
- **Blok data bilingual:** Voltage (resting/loaded), V-drop, Internal Resistance, Load Current,
  ΔTemp, Vision Score, Cycle time, Timestamp.
- **Sparkline** kurva discharge kecil (Voltage vs t) dari CSV bila tersedia.
- **Footer:** QR (kiri) + "Scan to verify authenticity · Pindai untuk verifikasi keaslian" +
  **kode tanda tangan** (12 hex pertama, mono) + pernyataan sertifikasi bilingual.

## 4. Keaslian (HMAC, offline)

- **Payload kanonik** urutan tetap: `RC1|{id}|{grade}|{soh:.1f}|{v_drop:.3f}|{internal_r:.4f}|{date}`.
- **Signature:** `HMAC-SHA256(payload, key)` hex.
- **String QR:** `"{payload}~{sig}"` (pemisah `~` tak muncul di payload).
- **Kunci** di `jetson/config/passport_key.txt`. Bila tak ada → dibuat otomatis `secrets.token_hex(32)`
  sekali & dipersist (log peringatan). File ini **di-`.gitignore`** (rahasia per-alat).
- **Verifikasi:** `verify(qr_string, key)` pisah payload/sig, hitung ulang HMAC, banding dgn
  `hmac.compare_digest`, parse field. Tool CLI `verify_passport.py "<qr>"` cetak **VALID/INVALID** + data.

## 5. Struktur modul (boundary bersih)

- **`jetson/src/passport_auth.py`** — *stdlib saja* (`hmac`, `hashlib`, `secrets`). API:
  - `canonical_payload(fields: dict) -> str`
  - `sign(fields: dict, key: str) -> str`
  - `build_qr_payload(fields: dict, key: str) -> str`
  - `verify(qr_string: str, key: str) -> tuple[bool, dict]`
  - `load_or_create_key(path: str) -> str`
  Bisa diuji penuh tanpa dependency berat.
- **`jetson/src/passport_generator.py`** — rendering reportlab; impor `passport_auth` + `qrcode`.
  Pertahankan kelas `BatteryPassport` & method `generate_pdf(...)` (interface lama) dgn parameter
  diperkaya. Dibungkus try/except: kegagalan render **tidak** menggagalkan siklus (log + return path/None).
- **`jetson/scripts/verify_passport.py`** — CLI verifikasi (baca key, terima QR string).

## 6. Integrasi `main.py`

- Ubah `battery_id` → `time.strftime("RC-%Y%m%d-%H%M%S")` (dipakai konsisten: log, foto, passport).
- Perluas pemanggilan `generate_pdf(...)` dengan `measurement=self.measurement_detail`,
  `defects=self.get_confirmed_defects()`, `timestamp=...`.
- `generate_pdf` signature:
  `generate_pdf(self, battery_id, grade, vision_score, volt, curr, soh, image_path, measurement=None, defects=None, timestamp=None)` (default mundur-kompatibel).

## 7. Ketahanan

- Foto hilang → kotak placeholder "NO PHOTO · Tanpa Foto".
- Font TTF tak ada → fallback font bawaan. CSV discharge tak ada → lewati sparkline.
- Kunci tak ada → auto-generate. Import reportlab/qrcode gagal → log error, return None; siklus jalan terus.

## 8. Testing

- **`tests/test_passport_auth.py`** (stdlib, jalan di env mana pun, gaya `__main__` runner seperti
  `test_protocol_sync.py`):
  - `sign` deterministik untuk input+key sama.
  - `verify` → `(True, data)` untuk payload baru; field data benar.
  - **tamper** (ubah grade/soh di QR) → `(False, ...)`.
  - kunci berbeda → invalid.
- **`tests/test_protocol_sync.py`** tetap hijau (perubahan main.py tidak menyentuh protokol).
- Smoke PDF (mesin ber-reportlab): generate dari data contoh → file PDF ada & >0 byte.

## 9. Dependency offline

- Tambah **`reportlab`** + **`qrcode`** ke `requirements-jetson-runtime.txt` (keduanya pure-Python →
  wheel aarch64 mudah). DEPLOY_GUIDE Tahap 1 otomatis mengunduhnya via `requirements-jetson-runtime.txt`.

## 10. Di luar cakupan (YAGNI)

- Multi-halaman / lampiran kurva penuh.
- Tanda tangan kunci-publik (PKI) — HMAC kunci simetris cukup untuk verifikasi offline di alat sendiri.
- Penyimpanan ke database; CSV log yang ada tetap dipakai.
- Bundling font TTF custom (hanya hook opsional; default font bawaan).
