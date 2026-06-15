"""Sertifikat Baterai Premium (A5 PDF, offline, anti-pemalsuan).

Mengganti template FPDF generik dengan sertifikat bergaya passport resmi:
bingkai guilloche emas, segel grade, data teknis bilingual (EN/ID), sparkline
kurva discharge, dan QR ber-HMAC (lihat passport_auth). Dirender dengan reportlab
(vektor, pure-Python -> jalan offline di Jetson air-gapped).

Tahan banting: seluruh proses dibungkus try/except — kegagalan render TIDAK
menggagalkan siklus grading (cukup log + return None). Foto/CSV/font yang hilang
ditangani dengan fallback yang rapi.
"""

import os
import csv
import math
from datetime import datetime
from pathlib import Path

import passport_auth

# Lokasi kunci rahasia per-alat (di-gitignore) -> jetson/config/passport_key.txt
_KEY_PATH = Path(__file__).resolve().parent.parent / "config" / "passport_key.txt"
# Direktori font opsional (drop TTF di sini untuk tampilan lebih khas).
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# --- Palet sertifikat premium ---------------------------------------------
CREAM   = "#F7F3E8"   # kertas
INK     = "#1A1A2E"   # tinta utama
GOLD    = "#B08D3E"   # aksen emas
GOLD_LT = "#D9C48F"   # guilloche/hairline terang
MUTED   = "#6B6B5E"   # teks sekunder
GRADE_COLORS = {"A": "#10B981", "B": "#F59E0B", "R": "#EF4444"}
GRADE_SUBTITLE = {
    "A": ("SECOND-LIFE COMPATIBLE", "Layak Pakai-Ulang"),
    "B": ("REFURBISH / LIMITED USE", "Rekondisi / Terbatas"),
    "R": ("REJECTED — RECYCLE",  "Ditolak — Daur Ulang"),
}


class BatteryPassport:
    def __init__(self, output_dir="passports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # --- API publik (interface dipertahankan, parameter diperkaya) ----------
    def generate_pdf(self, battery_id, grade, vision_score, volt, curr, soh,
                     image_path, measurement=None, defects=None, timestamp=None):
        try:
            return self._render(
                battery_id, grade, vision_score, volt, curr, soh, image_path,
                measurement or {}, defects or [],
                timestamp or datetime.now().isoformat(timespec="seconds"),
            )
        except ImportError as e:
            print(f"[Passport] reportlab/qrcode tidak tersedia ({e}); PDF dilewati.")
            return None
        except Exception as e:  # noqa: BLE001 - PDF tak boleh menjatuhkan siklus
            print(f"[Passport] Gagal membuat sertifikat ({e}); siklus tetap lanjut.")
            return None

    # --- Implementasi -------------------------------------------------------
    def _render(self, battery_id, grade, vision_score, volt, curr, soh,
                image_path, m, defects, timestamp):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A5
        from reportlab.lib.colors import HexColor

        fonts = self._register_fonts()
        W, H = A5  # A5 potret (~419.5 x 595.3 pt)
        path = os.path.join(self.output_dir, f"Passport_{battery_id}.pdf")
        c = canvas.Canvas(path, pagesize=A5)

        # Latar kertas cream
        c.setFillColor(HexColor(CREAM))
        c.rect(0, 0, W, H, stroke=0, fill=1)

        self._draw_border(c, HexColor, W, H)
        self._draw_guilloche(c, HexColor, W * 0.5, H - 132, 60)  # medallion samar di belakang seal kanan
        self._draw_header(c, HexColor, fonts, W, H)

        # Kolom kiri: foto + ID + defect
        photo_x, photo_w = 26, 150
        photo_h, photo_top = 112, H - 96
        self._draw_photo(c, HexColor, fonts, image_path, photo_x, photo_top - photo_h, photo_w, photo_h)
        self._draw_id_defects(c, HexColor, fonts, battery_id, defects,
                              photo_x, photo_top - photo_h - 14, photo_w)

        # Kolom kanan: segel grade + SoH
        seal_cx, seal_cy = W - 96, H - 132
        self._draw_grade_seal(c, HexColor, fonts, grade, seal_cx, seal_cy, 44)
        self._draw_soh(c, HexColor, fonts, soh, seal_cx, seal_cy - 78)

        # Blok data teknis bilingual
        rows = self._data_rows(m, volt, curr, soh, vision_score, timestamp)
        self._draw_data_block(c, HexColor, fonts, rows, 26, H - 250, W - 52)

        # Sparkline kurva discharge (dilewati bila tak ada data)
        self._draw_sparkline(c, HexColor, fonts, battery_id, 26, 132, W - 52, 70)

        # Footer: QR bertanda tangan + pernyataan
        self._draw_footer(c, HexColor, fonts, battery_id, grade, soh, m, timestamp, W)

        c.showPage()
        c.save()
        return path

    # --- Font ---------------------------------------------------------------
    def _register_fonts(self):
        """Pakai TTF dari assets/fonts bila ada; selain itu font bawaan reportlab."""
        fonts = {"serif": "Times-Roman", "serif_bold": "Times-Bold",
                 "sans": "Helvetica", "sans_bold": "Helvetica-Bold", "mono": "Courier"}
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            candidates = {
                "serif":      "PassportSerif.ttf",
                "serif_bold": "PassportSerif-Bold.ttf",
                "sans":       "PassportSans.ttf",
                "mono":       "PassportMono.ttf",
            }
            for key, fname in candidates.items():
                fpath = _FONT_DIR / fname
                if fpath.exists():
                    name = f"PP-{key}"
                    pdfmetrics.registerFont(TTFont(name, str(fpath)))
                    fonts[key] = name
        except Exception:
            pass  # fallback ke bawaan
        return fonts

    # --- Helper gambar ------------------------------------------------------
    def _draw_border(self, c, HexColor, W, H):
        c.setStrokeColor(HexColor(GOLD))
        c.setLineWidth(1.6); c.rect(14, 14, W - 28, H - 28, stroke=1, fill=0)
        c.setLineWidth(0.5); c.rect(19, 19, W - 38, H - 38, stroke=1, fill=0)

    def _draw_guilloche(self, c, HexColor, cx, cy, R):
        """Rosette parametrik samar (kesan ornamen sekuriti)."""
        c.saveState()
        c.setStrokeColor(HexColor(GOLD_LT)); c.setLineWidth(0.35)
        for petals in (5, 7):
            p = c.beginPath()
            steps = 540
            for i in range(steps + 1):
                th = (i / steps) * 2 * math.pi
                r = R * (0.55 + 0.45 * math.cos(petals * th))
                x = cx + r * math.cos(th); y = cy + r * math.sin(th)
                if i == 0:
                    p.moveTo(x, y)
                else:
                    p.lineTo(x, y)
            c.drawPath(p, stroke=1, fill=0)
        c.restoreState()

    def _draw_header(self, c, HexColor, fonts, W, H):
        c.setFillColor(HexColor(INK))
        c.setFont(fonts["serif_bold"], 26)
        c.drawCentredString(W / 2, H - 50, self._spaced("RECELL-AI"))
        c.setFillColor(HexColor(MUTED))
        c.setFont(fonts["sans"], 7.5)
        c.drawCentredString(W / 2, H - 63,
                            "DIGITAL BATTERY PASSPORT  ·  Paspor Baterai Digital")
        c.setStrokeColor(HexColor(GOLD)); c.setLineWidth(0.8)
        c.line(60, H - 72, W - 60, H - 72)

    def _draw_photo(self, c, HexColor, fonts, image_path, x, y, w, h):
        if image_path and os.path.exists(image_path):
            try:
                c.drawImage(image_path, x, y, width=w, height=h,
                            preserveAspectRatio=True, anchor='c', mask='auto')
            except Exception:
                self._photo_placeholder(c, HexColor, fonts, x, y, w, h)
        else:
            self._photo_placeholder(c, HexColor, fonts, x, y, w, h)
        # Bingkai sudut emas
        c.setStrokeColor(HexColor(GOLD)); c.setLineWidth(0.9)
        c.rect(x, y, w, h, stroke=1, fill=0)

    def _photo_placeholder(self, c, HexColor, fonts, x, y, w, h):
        c.setFillColor(HexColor("#ECE7D8"))
        c.rect(x, y, w, h, stroke=0, fill=1)
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 8)
        c.drawCentredString(x + w / 2, y + h / 2 + 4, "NO PHOTO")
        c.drawCentredString(x + w / 2, y + h / 2 - 7, "Tanpa Foto")

    def _draw_id_defects(self, c, HexColor, fonts, battery_id, defects, x, y, w):
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6)
        c.drawString(x, y, "UNIQUE ID  ·  ID Unik")
        c.setFillColor(HexColor(INK)); c.setFont(fonts["mono"], 10)
        c.drawString(x, y - 12, battery_id)
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6)
        c.drawString(x, y - 26, "DEFECTS  ·  Cacat Terdeteksi")
        if defects:
            c.setFillColor(HexColor(GRADE_COLORS["R"])); c.setFont(fonts["sans_bold"], 8)
            c.drawString(x, y - 37, ", ".join(defects))
        else:
            c.setFillColor(HexColor(GRADE_COLORS["A"])); c.setFont(fonts["sans_bold"], 8)
            c.drawString(x, y - 37, "No defects · Tanpa Cacat")

    def _draw_grade_seal(self, c, HexColor, fonts, grade, cx, cy, R):
        col = HexColor(GRADE_COLORS.get(grade, MUTED))
        c.setStrokeColor(col); c.setLineWidth(2.2); c.circle(cx, cy, R, stroke=1, fill=0)
        c.setLineWidth(0.8); c.circle(cx, cy, R - 5, stroke=1, fill=0)
        c.setFillColor(col); c.setFont(fonts["serif_bold"], 38)
        c.drawCentredString(cx, cy - 13, grade if grade in GRADE_COLORS else "?")
        c.setFont(fonts["sans"], 5.5); c.setFillColor(HexColor(MUTED))
        c.drawCentredString(cx, cy - R - 9, "GRADE")
        en, idn = GRADE_SUBTITLE.get(grade, ("UNGRADED", "Belum Dinilai"))
        c.setFillColor(col); c.setFont(fonts["sans_bold"], 6.5)
        c.drawCentredString(cx, cy - R - 20, en)
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6)
        c.drawCentredString(cx, cy - R - 30, idn)

    def _draw_soh(self, c, HexColor, fonts, soh, cx, y):
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6)
        c.drawCentredString(cx, y + 16, "STATE OF HEALTH · Kondisi Kesehatan")
        c.setFillColor(HexColor(INK)); c.setFont(fonts["serif_bold"], 22)
        c.drawCentredString(cx, y, f"{float(soh):.1f}%")
        # bar mini
        bw, bh = 96, 5
        bx, by = cx - bw / 2, y - 12
        c.setFillColor(HexColor("#E4DCC6")); c.rect(bx, by, bw, bh, stroke=0, fill=1)
        frac = max(0.0, min(1.0, float(soh) / 100.0))
        c.setFillColor(HexColor(GOLD)); c.rect(bx, by, bw * frac, bh, stroke=0, fill=1)

    def _data_rows(self, m, volt, curr, soh, vision_score, timestamp):
        def g(k, default):
            v = m.get(k, default)
            return v if v is not None else default
        return [
            ("RESTING VOLTAGE · Tegangan Diam",      f"{float(g('v_resting', 0.0)):.3f} V"),
            ("LOADED VOLTAGE · Tegangan Berbeban",   f"{float(g('v_loaded', volt)):.3f} V"),
            ("VOLTAGE DROP · Penurunan Tegangan",    f"{float(g('v_drop', 0.0)):.3f} V"),
            ("INTERNAL RESISTANCE · Resistansi Int", f"{float(g('internal_r', 0.0)):.4f} Ω"),
            ("LOAD CURRENT · Arus Beban",            f"{float(g('current_load', curr)):.3f} A"),
            ("TEMP RISE · Kenaikan Suhu",            f"{float(g('temp_delta', 0.0)):.2f} °C"),
            ("VISION SCORE · Skor Visual",           f"{float(vision_score):.2f} / 1.00"),
            ("ISSUED · Diterbitkan",                 str(timestamp)),
        ]

    def _draw_data_block(self, c, HexColor, fonts, rows, x, y_top, w):
        c.setStrokeColor(HexColor(GOLD)); c.setLineWidth(0.6)
        c.line(x, y_top + 6, x + w, y_top + 6)
        rh = 16
        for i, (label, value) in enumerate(rows):
            yy = y_top - i * rh
            c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 7.5)
            c.drawString(x + 2, yy, label)
            c.setFillColor(HexColor(INK)); c.setFont(fonts["mono"], 8.5)
            c.drawRightString(x + w - 2, yy, value)
            c.setStrokeColor(HexColor("#E8E1CE")); c.setLineWidth(0.3)
            c.line(x, yy - 5, x + w, yy - 5)

    def _draw_sparkline(self, c, HexColor, fonts, battery_id, x, y, w, h):
        pts = self._load_discharge(battery_id)
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6.5)
        c.drawString(x, y + h + 4, "DISCHARGE CURVE · Kurva Penurunan Tegangan (V vs t)")
        c.setStrokeColor(HexColor(GOLD_LT)); c.setLineWidth(0.4)
        c.rect(x, y, w, h, stroke=1, fill=0)
        if len(pts) < 2:
            c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 7)
            c.drawCentredString(x + w / 2, y + h / 2 - 3, "no curve data · tanpa data kurva")
            return
        ts = [p[0] for p in pts]; vs = [p[1] for p in pts]
        tmin, tmax = min(ts), max(ts); vmin, vmax = min(vs), max(vs)
        tspan = (tmax - tmin) or 1.0; vspan = (vmax - vmin) or 1.0
        pad = 6
        path = c.beginPath()
        for i, (t, v) in enumerate(pts):
            px = x + pad + (t - tmin) / tspan * (w - 2 * pad)
            py = y + pad + (v - vmin) / vspan * (h - 2 * pad)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        c.setStrokeColor(HexColor(GRADE_COLORS["A"])); c.setLineWidth(1.1)
        c.drawPath(path, stroke=1, fill=0)

    def _load_discharge(self, battery_id, limit=400):
        """Baca (t_ms, voltage) untuk battery_id dari data/logs/discharge_curve.csv."""
        csv_path = Path(self.output_dir).resolve().parent / "logs" / "discharge_curve.csv"
        pts = []
        try:
            if not csv_path.exists():
                return pts
            with open(csv_path, newline="") as f:
                for row in csv.reader(f):
                    # kolom: battery_id, t_ms, voltage, current, temp
                    if len(row) < 3 or row[0] != battery_id:
                        continue
                    try:
                        pts.append((float(row[1]), float(row[2])))
                    except ValueError:
                        continue
        except Exception:
            return []
        return pts[:limit]

    def _draw_footer(self, c, HexColor, fonts, battery_id, grade, soh, m, timestamp, W):
        key = passport_auth.load_or_create_key(str(_KEY_PATH))
        fields = {
            "id": battery_id, "grade": grade, "soh": soh,
            "v_drop": m.get("v_drop", 0.0), "internal_r": m.get("internal_r", 0.0),
            "date": timestamp,
        }
        qrstr = passport_auth.build_qr_payload(fields, key)
        sig = qrstr.rsplit("~", 1)[1][:12].upper()

        qx, qy, qsize = 26, 36, 72
        self._draw_qr(c, HexColor, qrstr, qx, qy, qsize)

        tx = qx + qsize + 14
        c.setFillColor(HexColor(INK)); c.setFont(fonts["sans_bold"], 7.5)
        c.drawString(tx, qy + qsize - 8, "Scan to verify authenticity")
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 7)
        c.drawString(tx, qy + qsize - 18, "Pindai untuk verifikasi keaslian")
        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6)
        c.drawString(tx, qy + qsize - 33, "SIGNATURE · Tanda Tangan")
        c.setFillColor(HexColor(GOLD)); c.setFont(fonts["mono"], 9)
        c.drawString(tx, qy + qsize - 45, sig)

        c.setFillColor(HexColor(MUTED)); c.setFont(fonts["sans"], 6)
        c.drawCentredString(W / 2, 24,
                            "This certificate verifies automated second-life battery testing by RECELL-AI.")
        c.drawCentredString(W / 2, 16,
                            "Sertifikat ini memverifikasi pengujian otomatis baterai pakai-ulang oleh RECELL-AI.")

    def _draw_qr(self, c, HexColor, qrstr, x, y, size):
        import qrcode
        qr = qrcode.QRCode(border=0, box_size=1,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(qrstr); qr.make(fit=True)
        matrix = qr.get_matrix()
        n = len(matrix)
        cell = size / n
        c.setFillColor(HexColor(INK))
        for r, row in enumerate(matrix):
            for ci, val in enumerate(row):
                if val:
                    c.rect(x + ci * cell, y + (n - 1 - r) * cell, cell, cell,
                           stroke=0, fill=1)

    # --- util ---------------------------------------------------------------
    @staticmethod
    def _spaced(text):
        return " ".join(list(text))  # spasi-huruf tipis untuk wordmark
