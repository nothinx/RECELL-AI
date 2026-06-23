#!/usr/bin/env python3
"""GUI capture dataset — untuk operator/teman, tanpa CLI.

Single-label classification: pilih KELAS dulu, lalu AMBIL → burst gambar
tersimpan ke folder kelas itu (auto-terlabel). Tak perlu anotasi terpisah.

    datasets/capture/{KOSONG,SEHAT,KARAT,SOBEK}/cap_*.jpg

PENTING: service `recell` memegang kamera. Hentikan dulu:
    sudo systemctl stop recell
    python3 jetson/scripts/capture_gui.py
    sudo systemctl start recell

Setelan kamera identik app (848x480, MJPG, focus 115) — via capture_dataset.
Label baterai >1 cacat dgn yang TERKRITIS (prioritas SOBEK > KARAT > SEHAT).
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QGridLayout, QSpinBox,
)

from capture_dataset import open_camera, lock_focus  # reuse setelan kamera

CLASSES = ["KOSONG", "SEHAT", "KARAT", "SOBEK"]
COLORS = {"KOSONG": "#64748B", "SEHAT": "#10B981", "KARAT": "#F59E0B", "SOBEK": "#EF4444"}


class CaptureGUI(QWidget):
    def __init__(self, out_root, index):
        super().__init__()
        self.out_root = Path(out_root)
        self.index = index
        self.active = "SEHAT"
        for c in CLASSES:
            (self.out_root / c).mkdir(parents=True, exist_ok=True)

        self.cap = open_camera(index)
        self.cap.read(); time.sleep(0.3); lock_focus(self.cap, index)
        self._last_frame = None

        self.setWindowTitle("RECELL-AI · Capture Dataset")
        self.setStyleSheet("background:#0F172A; color:#E2E8F0; font-size:14px;")
        self._build()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)  # ~30 fps preview

    def _build(self):
        root = QHBoxLayout(self)

        self.view = QLabel("memuat kamera…")
        self.view.setFixedSize(848, 480)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background:#000; border:1px solid #334155; border-radius:8px;")
        root.addWidget(self.view)

        side = QVBoxLayout()
        side.setSpacing(14)
        side.addWidget(self._lbl("KELAS (pilih dulu):", 13, "#94A3B8"))

        self.class_btns = {}
        grid = QGridLayout()
        for i, c in enumerate(CLASSES):
            b = QPushButton(c)
            b.setMinimumHeight(64)
            b.clicked.connect(lambda _, cls=c: self._set_active(cls))
            self.class_btns[c] = b
            grid.addWidget(b, i // 2, i % 2)
        side.addLayout(grid)

        burst_row = QHBoxLayout()
        burst_row.addWidget(self._lbl("Jumlah / AMBIL:", 13, "#94A3B8"))
        self.spin = QSpinBox()
        self.spin.setRange(1, 100)
        self.spin.setValue(8)
        self.spin.setStyleSheet("background:#1E293B; padding:8px; font-size:16px; font-weight:700;")
        burst_row.addWidget(self.spin)
        burst_row.addStretch(1)
        side.addLayout(burst_row)

        self.take = QPushButton("📸  AMBIL")
        self.take.setMinimumHeight(80)
        self.take.setStyleSheet(
            "background:#2563EB; color:white; font-size:22px; font-weight:900; border-radius:10px;")
        self.take.clicked.connect(self._capture_burst)
        side.addWidget(self.take)

        side.addWidget(self._lbl("Tersimpan:", 13, "#94A3B8"))
        self.counts = {}
        for c in CLASSES:
            lab = self._lbl("", 15, COLORS[c])
            self.counts[c] = lab
            side.addWidget(lab)

        self.status = self._lbl("", 12, "#94A3B8")
        side.addWidget(self.status)
        side.addStretch(1)
        root.addLayout(side)

        self._set_active(self.active)
        self._refresh_counts()

    def _lbl(self, text, size, color):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:700;")
        return l

    def _set_active(self, cls):
        self.active = cls
        for c, b in self.class_btns.items():
            if c == cls:
                b.setStyleSheet(f"background:{COLORS[c]}; color:white; font-size:18px; "
                                f"font-weight:900; border:3px solid white; border-radius:10px;")
            else:
                b.setStyleSheet(f"background:#1E293B; color:{COLORS[c]}; font-size:16px; "
                                f"font-weight:800; border:1px solid #334155; border-radius:10px;")

    def _count(self, cls):
        return sum(1 for _ in (self.out_root / cls).glob("*.jpg"))

    def _refresh_counts(self):
        for c in CLASSES:
            self.counts[c].setText(f"{c}: {self._count(c)}")

    def _tick(self):
        ok, frame = self.cap.read()
        if not ok:
            return
        self._last_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(img).scaled(
            self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _capture_burst(self):
        cls = self.active
        n = self.spin.value()
        self.take.setEnabled(False)
        saved = 0
        for _ in range(n):
            ok, frame = self.cap.read()
            if not ok:
                continue
            name = self.out_root / cls / f"cap_{datetime.now():%Y%m%d-%H%M%S-%f}.jpg"
            cv2.imwrite(str(name), frame)
            saved += 1
            self.status.setText(f"  ambil {cls}… {saved}/{n}")
            QApplication.processEvents()   # jaga UI responsif + frame segar
            time.sleep(0.12)
        self._refresh_counts()
        self.status.setText(f"  ✓ {saved} gambar {cls} tersimpan.")
        self.take.setEnabled(True)

    def closeEvent(self, e):
        self.timer.stop()
        self.cap.release()
        e.accept()


def main():
    ap = argparse.ArgumentParser(description="GUI capture dataset (single-label).")
    ap.add_argument("--out", default="datasets/capture")
    ap.add_argument("--index", type=int, default=0)
    args = ap.parse_args()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = CaptureGUI(args.out, args.index)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
