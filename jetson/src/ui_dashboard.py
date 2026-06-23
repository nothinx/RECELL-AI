"""RECELL-AI Industrial HMI Dashboard.

Tier-1 PyQt5 dashboard that wraps RecellMaster. Designed for the Jetson Orin
Nano's display but works on any desktop Linux with Qt.
"""

import sys
import subprocess
import cv2
import numpy as np
import threading
import time
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QFrame, QPlainTextEdit, QProgressBar, QSizePolicy, QGraphicsDropShadowEffect,
    QDialog, QComboBox, QSpinBox, QDialogButtonBox, QListWidget, QListWidgetItem,
    QFormLayout, QTabWidget, QGridLayout,
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QImage, QPixmap, QColor
import pyqtgraph as pg

# NOTE: OpenGL renders slightly faster on Jetson but the resulting GraphicsView
# surface isn't captured by Qt's `widget.grab()` (used for screenshots) and on
# some desktop Linux setups it falls back to a white background. Keeping it
# off here gives consistent visuals everywhere. Re-enable on Jetson if FPS
# becomes an issue with very long discharge buffers.
pg.setConfigOptions(useOpenGL=False, antialias=True)

from main import RecellMaster


# ----- THEME (light, colorful) ----------------------------------------------
COL_BG          = "#F4F6FB"   # window background — soft cool white
COL_SURFACE     = "#FFFFFF"   # cards
COL_SURFACE_ALT = "#F1F5F9"   # nested / camera viewport / plot bg
COL_BORDER      = "#E2E8F0"   # hairline border
COL_TEXT        = "#0F172A"   # slate-900 main text
COL_HEADING     = "#1E293B"   # slate-800 (card titles)
COL_MUTED       = "#64748B"   # slate-500
COL_ACCENT      = "#10B981"   # emerald 500 — FILLS only (dots, plot, button bg)
COL_INFO        = "#3B82F6"   # blue 500 — fills
COL_WARN        = "#F59E0B"   # amber 500 — fills
COL_PURPLE      = "#8B5CF6"   # violet 500 (vision / accent variety)
COL_ERROR       = "#EF4444"   # red 500 — fills (stop button bg, chips)
COL_STANDBY     = "#94A3B8"   # slate-400

# Text-on-light variants — darker shades so large headline values (grade, SOH,
# voltage) clear WCAG contrast on white/pale backgrounds. The -500 tokens above
# wash out as text (≈2.1–2.5:1); these land at ≈4.8–5.9:1. Use for TEXT, never fills.
COL_ACCENT_TXT  = "#047857"   # emerald 700
COL_INFO_TXT    = "#2563EB"   # blue 600
COL_WARN_TXT    = "#B45309"   # amber 700
COL_ERROR_TXT   = "#B91C1C"   # red 700


GRADE_COLORS = {
    # (text color, subtitle, soft bg, border)
    "A": (COL_ACCENT_TXT, "Second-Life Compatible",  "#ECFDF5", "#A7F3D0"),
    "B": (COL_WARN_TXT,   "Refurbish / Limited Use", "#FFFBEB", "#FDE68A"),
    "R": (COL_ERROR_TXT,  "Rejected (Recycle)",      "#FEF2F2", "#FECACA"),
}


GLOBAL_QSS = f"""
QMainWindow, QWidget#root {{ background-color: {COL_BG}; color: {COL_TEXT}; }}
QLabel {{ color: {COL_TEXT}; }}
QLabel[role="muted"] {{ color: {COL_MUTED}; }}
QFrame[role="card"] {{
    background-color: {COL_SURFACE};
    border: 1px solid {COL_BORDER};
    border-radius: 12px;
}}
QLabel[role="cardTitle"] {{
    color: {COL_MUTED};
    font-size: 11px;
    letter-spacing: 1.6px;
    font-weight: 700;
}}
QPushButton {{
    border: none; border-radius: 10px; padding: 12px 18px;
    font-weight: 700; font-size: 13px; letter-spacing: 0.4px;
}}
QPushButton#btnStart {{ background-color: {COL_ACCENT}; color: white; }}
QPushButton#btnStart:hover {{ background-color: #059669; }}
QPushButton#btnStart:pressed {{ background-color: #047857; }}
QPushButton#btnStart:disabled {{ background-color: #D1FAE5; color: {COL_ACCENT_TXT}; }}
QPushButton#btnStop {{ background-color: {COL_ERROR}; color: white; }}
QPushButton#btnStop:hover {{ background-color: #DC2626; }}
QPushButton#btnStop:pressed {{ background-color: #B91C1C; }}
QPlainTextEdit {{
    background-color: {COL_SURFACE_ALT};
    color: {COL_HEADING};
    border: 1px solid {COL_BORDER};
    border-radius: 8px;
    selection-background-color: {COL_INFO};
    selection-color: white;
}}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COL_BORDER}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {COL_STANDBY}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QProgressBar {{
    border: 1px solid {COL_BORDER}; border-radius: 10px;
    background-color: {COL_SURFACE_ALT}; text-align: center;
    font-weight: 700; color: {COL_HEADING}; height: 22px;
}}
QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COL_INFO}, stop:0.5 {COL_PURPLE}, stop:1 {COL_ACCENT});
    border-radius: 8px;
}}
"""


# ----- WIDGETS --------------------------------------------------------------
class Card(QFrame):
    """A bordered surface card with optional title and colored top accent."""
    def __init__(self, title=None, accent=None, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(8)
        if title:
            title_row = QHBoxLayout()
            title_row.setSpacing(8)
            if accent:
                dot = QLabel()
                dot.setFixedSize(8, 8)
                dot.setStyleSheet(f"background-color:{accent}; border-radius:4px;")
                title_row.addWidget(dot)
            lab = QLabel(title.upper())
            lab.setProperty("role", "cardTitle")
            title_row.addWidget(lab)
            title_row.addStretch(1)
            outer.addLayout(title_row)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)


class StatusPill(QFrame):
    """A small pill showing a label and a colored dot. Optionally clickable."""
    clicked = pyqtSignal()

    def __init__(self, label, clickable=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self._clickable = clickable
        self._base_style = (
            f"background-color:{COL_SURFACE}; border:1px solid {COL_BORDER};"
            f"border-radius:15px;"
        )
        self.setStyleSheet(self._base_style)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 14, 0)
        lay.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(
            f"color:{COL_HEADING}; font-size:11px; font-weight:700; letter-spacing:0.6px;"
        )
        self.val = QLabel("--")
        self.val.setStyleSheet(
            f"color:{COL_MUTED}; font-size:11px; font-weight:800;"
        )
        lay.addWidget(self.dot)
        lay.addWidget(self.lbl)
        lay.addWidget(self.val)
        self.set_state("offline")

    def mousePressEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_state(self, state):
        states = {
            "online":  (COL_ACCENT,   "ONLINE"),
            "sim":     (COL_INFO,     "SIM"),
            "mock":    (COL_WARN,     "MOCK"),
            "rule":    (COL_WARN,     "RULE"),
            "stale":   (COL_WARN,     "STALE"),
            "offline": (COL_STANDBY,  "OFFLINE"),
        }
        color, text = states.get(state, states["offline"])
        self.dot.setStyleSheet(f"background-color:{color}; border-radius:5px;")
        self.val.setText(text)
        self.val.setStyleSheet(f"color:{color}; font-size:11px; font-weight:800;")


class MetricCard(Card):
    """A card displaying one big metric value with a unit and subtitle."""
    def __init__(self, title, unit, accent=COL_TEXT, value_color=None, parent=None):
        super().__init__(title=title, accent=accent, parent=parent)
        self.accent = accent
        # Dot keeps the bright accent; the big value uses a darker, readable
        # shade (value_color) so it clears contrast on the white card.
        value_color = value_color or accent
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setAlignment(Qt.AlignBottom)

        self.value_lbl = QLabel("--")
        f = QFont("Inter", 30, QFont.Bold)
        f.setStyleStrategy(QFont.PreferAntialias)
        self.value_lbl.setFont(f)
        self.value_lbl.setStyleSheet(f"color:{value_color};")

        self.unit_lbl = QLabel(unit)
        self.unit_lbl.setStyleSheet(
            f"color:{COL_MUTED}; font-size:13px; font-weight:600; padding-bottom:7px;"
        )

        row.addWidget(self.value_lbl)
        row.addWidget(self.unit_lbl)
        row.addStretch(1)
        self.body.addLayout(row)

        self.sub_lbl = QLabel("")
        self.sub_lbl.setStyleSheet(f"color:{COL_MUTED}; font-size:11px;")
        self.body.addWidget(self.sub_lbl)

    def set_value(self, text, subtitle=None):
        self.value_lbl.setText(text)
        if subtitle is not None:
            self.sub_lbl.setText(subtitle)


class GradeCard(Card):
    """The hero card showing the final grade decision."""
    def __init__(self, parent=None):
        super().__init__(title="FINAL GRADING DECISION", parent=parent)
        self._inner = QFrame()
        self._inner.setStyleSheet(
            f"background-color:{COL_SURFACE_ALT}; border:1px solid {COL_BORDER};"
            f"border-radius:10px;"
        )
        inner_lay = QVBoxLayout(self._inner)
        inner_lay.setContentsMargins(12, 16, 12, 16)
        inner_lay.setSpacing(4)

        self.value_lbl = QLabel("STANDBY")
        f = QFont("Inter", 52, QFont.Black)
        self.value_lbl.setFont(f)
        self.value_lbl.setAlignment(Qt.AlignCenter)
        self.value_lbl.setStyleSheet(
            f"color:{COL_STANDBY}; background:transparent;"
        )
        self.sub_lbl = QLabel("AWAITING TRIGGER")
        self.sub_lbl.setAlignment(Qt.AlignCenter)
        self.sub_lbl.setStyleSheet(
            f"color:{COL_MUTED}; font-size:11px; letter-spacing:2.5px; font-weight:700;"
        )
        inner_lay.addWidget(self.value_lbl)
        inner_lay.addWidget(self.sub_lbl)
        self.body.addWidget(self._inner)

    def _style_inner(self, bg, border):
        self._inner.setStyleSheet(
            f"background-color:{bg}; border:1px solid {border}; border-radius:10px;"
        )

    def set_grade(self, grade):
        if grade in GRADE_COLORS:
            color, subtitle, bg, border = GRADE_COLORS[grade]
            self.value_lbl.setText(f"GRADE  {grade}")
            self.value_lbl.setStyleSheet(f"color:{color}; background:transparent;")
            self.sub_lbl.setText(subtitle.upper())
            self.sub_lbl.setStyleSheet(
                f"color:{color}; font-size:11px; letter-spacing:2.5px; font-weight:800;"
            )
            self._style_inner(bg, border)
        else:
            # Generic state (STANDBY, TESTING, ABORTED, etc.) — pick color
            # by keyword. Caller may also overwrite the text directly.
            self.value_lbl.setText(grade)
            self.value_lbl.setStyleSheet(
                f"color:{COL_STANDBY}; background:transparent;"
            )
            self.sub_lbl.setText("")
            self._style_inner(COL_SURFACE_ALT, COL_BORDER)

    def set_state(self, text, color, subtitle, bg=None, border=None):
        self.value_lbl.setText(text)
        self.value_lbl.setStyleSheet(f"color:{color}; background:transparent;")
        self.sub_lbl.setText(subtitle.upper())
        self.sub_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; letter-spacing:2.5px; font-weight:800;"
        )
        self._style_inner(bg or COL_SURFACE_ALT, border or COL_BORDER)


class DefectChip(QLabel):
    def __init__(self, label, color=COL_WARN, parent=None):
        super().__init__(f"  {label}  ", parent)
        self.setStyleSheet(
            f"background-color:{color}; color:white; border-radius:10px; "
            f"font-size:11px; font-weight:800; padding:4px 10px; "
            f"letter-spacing:0.5px;"
        )
        self.setAlignment(Qt.AlignCenter)


# ----- SERIAL CONFIG DIALOG -------------------------------------------------
class SerialConfigDialog(QDialog):
    """Modal dialog to scan, select, and connect to a serial port."""

    def __init__(self, master, parent=None):
        super().__init__(parent)
        self.master = master
        self.setWindowTitle("Konfigurasi Port Serial — STM32")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background:{COL_BG}; color:{COL_TEXT}; }}
            QLabel  {{ color:{COL_TEXT}; }}
            QComboBox, QSpinBox, QListWidget {{
                background:{COL_SURFACE}; color:{COL_TEXT};
                border:1px solid {COL_BORDER}; border-radius:6px; padding:4px 8px;
                font-size:13px;
            }}
            QComboBox::drop-down {{ border:none; }}
            QPushButton {{
                border:none; border-radius:8px; padding:8px 16px;
                font-weight:700; font-size:12px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 18, 20, 18)

        # Status baris atas
        status_row = QHBoxLayout()
        self._status_dot = QLabel()
        self._status_dot.setFixedSize(10, 10)
        self._status_lbl = QLabel("—")
        self._status_lbl.setStyleSheet(f"color:{COL_MUTED}; font-size:12px; font-weight:700;")
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()
        lay.addLayout(status_row)

        # Port list
        lbl_port = QLabel("Port yang tersedia:")
        lbl_port.setStyleSheet(f"color:{COL_HEADING}; font-weight:700; font-size:12px;")
        lay.addWidget(lbl_port)

        self.port_list = QListWidget()
        self.port_list.setFixedHeight(140)
        self.port_list.setStyleSheet(
            f"QListWidget::item:selected {{ background:{COL_INFO}; color:white; }}"
            f"QListWidget::item {{ padding:6px 8px; }}"
        )
        lay.addWidget(self.port_list)

        refresh_btn = QPushButton("↻  Refresh Ports")
        refresh_btn.setStyleSheet(
            f"background:{COL_SURFACE_ALT}; color:{COL_HEADING}; border:1px solid {COL_BORDER};"
        )
        refresh_btn.clicked.connect(self._scan_ports)
        lay.addWidget(refresh_btn)

        # Baud rate
        baud_row = QHBoxLayout()
        baud_lbl = QLabel("Baud Rate:")
        baud_lbl.setStyleSheet(f"color:{COL_HEADING}; font-weight:700; font-size:12px;")
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(9600, 921600)
        self.baud_spin.setSingleStep(9600)
        self.baud_spin.setValue(115200)
        self.baud_spin.setFixedWidth(120)
        baud_row.addWidget(baud_lbl)
        baud_row.addWidget(self.baud_spin)
        baud_row.addStretch()
        lay.addLayout(baud_row)

        # Tombol aksi
        btn_row = QHBoxLayout()
        self.btn_connect = QPushButton("Hubungkan")
        self.btn_connect.setStyleSheet(f"background:{COL_ACCENT}; color:white;")
        self.btn_connect.clicked.connect(self._do_connect)

        self.btn_disconnect = QPushButton("Putuskan")
        self.btn_disconnect.setStyleSheet(f"background:{COL_ERROR}; color:white;")
        self.btn_disconnect.clicked.connect(self._do_disconnect)

        close_btn = QPushButton("Tutup")
        close_btn.setStyleSheet(
            f"background:{COL_SURFACE_ALT}; color:{COL_HEADING}; border:1px solid {COL_BORDER};"
        )
        close_btn.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._scan_ports()
        self._refresh_status()

    def _scan_ports(self):
        self.port_list.clear()
        ports = self.master.list_serial_ports()
        if ports:
            for dev, desc in ports:
                item = QListWidgetItem(f"{dev}  —  {desc}")
                item.setData(Qt.UserRole, dev)
                self.port_list.addItem(item)
            self.port_list.setCurrentRow(0)
        else:
            item = QListWidgetItem("Tidak ada port yang terdeteksi")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.port_list.addItem(item)

    def _refresh_status(self):
        state = self.master.status.get("serial", "offline")
        colors = {"online": COL_ACCENT, "sim": COL_WARN, "offline": COL_ERROR}
        labels = {
            "online":  f"ONLINE — {getattr(self.master.ser, 'port', '?')}",
            "sim":     "SIMULASI (tidak ada perangkat)",
            "offline": "OFFLINE",
        }
        color = colors.get(state, COL_STANDBY)
        self._status_dot.setStyleSheet(f"background:{color}; border-radius:5px;")
        self._status_lbl.setText(labels.get(state, state.upper()))
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:12px; font-weight:700;")
        self.btn_disconnect.setEnabled(state == "online")

    def _do_connect(self):
        item = self.port_list.currentItem()
        if not item:
            return
        port = item.data(Qt.UserRole)
        if not port:
            return
        baud = self.baud_spin.value()
        self.btn_connect.setText("Menghubungkan…")
        self.btn_connect.setEnabled(False)
        ok = self.master.reconnect_serial(port, baud)
        self.btn_connect.setText("Hubungkan")
        self.btn_connect.setEnabled(True)
        self._refresh_status()
        if not ok:
            self._status_lbl.setText(f"Gagal terhubung ke {port}")

    def _do_disconnect(self):
        self.master.disconnect_serial()
        self._refresh_status()


# ----- CALIBRATION DIALOG ---------------------------------------------------
# Parameter tunable: (key, label, min, max, step). Urutan = tampilan di tab.
CALIB_FIELDS = [
    ("conveyor_speed",    "Conveyor speed (PWM 0–255)",      0,  255,   5),
    ("step_pulse_us",     "Stepper pulse target (µs, ↑=pelan)", 20, 5000, 10),
    ("ramp_start_us",     "Ramp start (µs, awal pelan)",      20, 5000,  50),
    ("ramp_steps",        "Ramp panjang (step)",              0,  5000,  50),
    ("dac_load",          "DAC beban (0–4095)",               0,  4095, 100),
    ("discharge_samples", "Sampel discharge",                 1,  500,    5),
    ("discharge_period",  "Periode discharge (ms)",           5,  1000,   5),
    ("ir2_settle",        "IR2 settle (ms)",                  0,  5000,  50),
]

# Indikator sensor digital di tab Monitor: (key, label, active_is_bad)
DIAG_DIGITAL = [
    ("ir_d",  "IR Ukur",       False),
    ("ir_s",  "IR Sorting",    False),
    ("ir_b",  "IR Backup",     False),
    ("lim_d", "Limit Ukur",    False),
    ("lim_s", "Limit Sorting", False),
    ("emg",   "Emergency",     True),   # aktif = bahaya → merah
]


class CalibrationDialog(QDialog):
    """Panel diagnostik & kalibrasi ber-tab (Monitor / Parameter / Manual).

    Dibuka dari tombol layar atau F12. Saat terbuka, firmware stream snapshot
    sensor (~5 Hz) ke tab Monitor. Parameter: Apply live + Simpan ke
    calibration.json. Manual: gerakkan tiap aktuator sendiri untuk diagnosa.
    """
    def __init__(self, master, parent=None):
        super().__init__(parent)
        self.master = master
        self.setWindowTitle("Kalibrasi — Setup Kecepatan")
        self.setMinimumSize(520, 460)
        self.setStyleSheet(f"""
            QDialog {{ background:{COL_BG}; color:{COL_TEXT}; }}
            QLabel  {{ color:{COL_TEXT}; }}
            QSpinBox {{
                background:{COL_SURFACE}; color:{COL_TEXT};
                border:1px solid {COL_BORDER}; border-radius:6px; padding:6px 8px;
                font-size:14px; font-weight:700; min-width:90px;
            }}
            QPushButton {{
                border:none; border-radius:8px; padding:9px 14px;
                font-weight:700; font-size:12px;
            }}
            QTabBar::tab {{
                background:{COL_SURFACE_ALT}; color:{COL_HEADING};
                padding:10px 22px; font-weight:700; font-size:13px;
                border:1px solid {COL_BORDER}; border-bottom:none;
                border-top-left-radius:8px; border-top-right-radius:8px;
            }}
            QTabBar::tab:selected {{ background:{COL_ACCENT}; color:white; }}
            QTabWidget::pane {{ border:1px solid {COL_BORDER}; border-radius:8px; top:-1px; }}
        """)

        self._mon = {}   # key -> (dot_label, value_label)
        self._spins = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_monitor_tab(), "Monitor")
        tabs.addTab(self._build_param_tab(), "Parameter")
        tabs.addTab(self._build_manual_tab(), "Manual")
        lay.addWidget(tabs)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QPushButton("Tutup")
        btn_close.setStyleSheet(
            f"background:{COL_SURFACE_ALT}; color:{COL_HEADING}; border:1px solid {COL_BORDER};")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        lay.addLayout(close_row)

    # ---- TAB: MONITOR ------------------------------------------------------
    def _build_monitor_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        # Kolom kiri: input digital (dot warna). Kolom kanan: analog + status.
        for r, (key, label, _bad) in enumerate(DIAG_DIGITAL):
            dot = QLabel()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(self._dot_qss(COL_MUTED))
            name = QLabel(label)
            name.setStyleSheet(f"color:{COL_HEADING}; font-size:13px; font-weight:600;")
            grid.addWidget(dot, r, 0)
            grid.addWidget(name, r, 1)
            self._mon[key] = (dot, None)

        analog = [
            ("v", "Tegangan"), ("i", "Arus"),
            ("t_obj", "Suhu objek"), ("t_amb", "Suhu ambient"),
            ("st", "State"), ("rdy", "Sensor I2C"),
        ]
        for r, (key, label) in enumerate(analog):
            name = QLabel(label)
            name.setStyleSheet(f"color:{COL_MUTED}; font-size:12px; font-weight:600;")
            val = QLabel("—")
            val.setStyleSheet(f"color:{COL_HEADING}; font-size:14px; font-weight:800;")
            grid.addWidget(name, r, 3)
            grid.addWidget(val, r, 4)
            self._mon[key] = (None, val)

        hint = QLabel("Gerakkan baterai / tekan sensor — indikator update live.")
        hint.setStyleSheet(f"color:{COL_MUTED}; font-size:11px; font-weight:600;")
        grid.addWidget(hint, len(DIAG_DIGITAL), 0, 1, 5)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(len(DIAG_DIGITAL) + 1, 1)
        return w

    def _dot_qss(self, color):
        return f"background:{color}; border-radius:8px;"

    def update_monitor(self, d):
        """Dipanggil dari main thread dgn snapshot DIAG firmware."""
        for key, _label, bad in DIAG_DIGITAL:
            dot, _ = self._mon.get(key, (None, None))
            if dot is None:
                continue
            active = bool(d.get(key, 0))
            if active:
                color = COL_ERROR if bad else COL_ACCENT
            else:
                color = COL_MUTED
            dot.setStyleSheet(self._dot_qss(color))
        def setv(key, text):
            pair = self._mon.get(key)
            if pair and pair[1] is not None:
                pair[1].setText(text)
        setv("v", f"{float(d.get('v', 0)):.3f} V")
        setv("i", f"{float(d.get('i', 0)):.3f} A")
        setv("t_obj", f"{float(d.get('t_obj', 0)):.1f} °C")
        setv("t_amb", f"{float(d.get('t_amb', 0)):.1f} °C")
        setv("st", str(d.get("st", "—")))
        rdy = d.get("rdy", {})
        setv("rdy", f"INA {'✓' if rdy.get('ina') else '✗'}  "
                    f"MLX {'✓' if rdy.get('mlx') else '✗'}  "
                    f"DAC {'✓' if rdy.get('dac') else '✗'}")

    # ---- TAB: PARAMETER ----------------------------------------------------
    def _build_param_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(9)
        cal = self.master.calibration
        for key, label, lo, hi, step in CALIB_FIELDS:
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setValue(int(cal.get(key, lo)))
            self._spins[key] = spin
            form.addRow(self._lbl(label), spin)
        lay.addLayout(form)
        lay.addStretch(1)

        act = QHBoxLayout()
        btn_apply = QPushButton("Apply (live)")
        btn_apply.setStyleSheet(
            f"background:{COL_SURFACE_ALT}; color:{COL_HEADING}; border:1px solid {COL_BORDER};")
        btn_apply.clicked.connect(lambda: self._apply(save=False))
        btn_save = QPushButton("Simpan")
        btn_save.setStyleSheet(f"background:{COL_ACCENT}; color:white;")
        btn_save.clicked.connect(lambda: self._apply(save=True))
        act.addStretch(1)
        act.addWidget(btn_apply)
        act.addWidget(btn_save)
        lay.addLayout(act)
        return w

    def _apply(self, save):
        updates = {k: s.value() for k, s in self._spins.items()}
        self.master.update_calibration(updates, save=save)

    # ---- TAB: MANUAL -------------------------------------------------------
    def _build_manual_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Jog step count untuk jog mentah.
        steprow = QHBoxLayout()
        steprow.addWidget(self._lbl("Jog mentah (step):"))
        self.spin_jog = QSpinBox()
        self.spin_jog.setRange(10, 2000)
        self.spin_jog.setSingleStep(50)
        self.spin_jog.setValue(200)
        steprow.addWidget(self.spin_jog)
        steprow.addStretch(1)
        lay.addLayout(steprow)

        lay.addWidget(self._section("Konveyor"))
        lay.addLayout(self._btn_row([
            ("◀ Mundur", COL_INFO,  lambda: self.master.conveyor_manual("rev")),
            ("▶ Maju",   COL_INFO,  lambda: self.master.conveyor_manual("fwd")),
            ("■ Stop",   COL_ERROR, lambda: self.master.conveyor_manual("stop")),
        ]))

        for which, title in (("drain", "Stepper Ukur"), ("sort", "Stepper Sorting")):
            lay.addWidget(self._section(title))
            lay.addLayout(self._btn_row([
                ("◀ Jog mundur", COL_INFO, lambda w=which: self.master.jog_stepper(w, "rev", self.spin_jog.value())),
                ("▶ Jog maju",   COL_INFO, lambda w=which: self.master.jog_stepper(w, "fwd", self.spin_jog.value())),
                ("⌂ Ke home",    COL_ACCENT, lambda w=which: self.master.home_stepper(w)),
            ]))

        lay.addWidget(self._section("Beban DAC"))
        lay.addLayout(self._btn_row([
            ("⚡ Beban ON",  COL_WARN,  lambda: self.master.dac_load(True)),
            ("○ Beban OFF", COL_INFO,  lambda: self.master.dac_load(False)),
        ]))

        lay.addStretch(1)
        lay.addLayout(self._btn_row([
            ("↺ RESET",      COL_SURFACE_ALT, lambda: self.master.send_command("RESET")),
            ("■ STOP semua", COL_ERROR,       self._stop_all),
        ]))
        return w

    def _stop_all(self):
        self.master.conveyor_manual("stop")
        self.master.dac_load(False)

    def _section(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{COL_HEADING}; font-size:12px; font-weight:800; margin-top:4px;")
        return l

    def _btn_row(self, specs):
        row = QHBoxLayout()
        for label, bg, cb in specs:
            b = QPushButton(label)
            fg = COL_HEADING if bg == COL_SURFACE_ALT else "white"
            border = f"border:1px solid {COL_BORDER};" if bg == COL_SURFACE_ALT else ""
            b.setStyleSheet(f"background:{bg}; color:{fg}; {border}")
            b.clicked.connect(cb)
            row.addWidget(b)
        return row

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{COL_HEADING}; font-size:12px; font-weight:600;")
        return l


class StatsDialog(QDialog):
    """Dashboard produksi: hitungan hari ini/total, distribusi grade A/B/R,
    rata-rata waktu siklus. Baca agregat dari grading_log.csv. Plus export
    semua log + passport ke USB flashdisk untuk operator."""
    def __init__(self, master, parent=None):
        super().__init__(parent)
        self.master = master
        self.setWindowTitle("Statistik Produksi")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background:{COL_BG}; color:{COL_TEXT}; }}
            QLabel  {{ color:{COL_TEXT}; }}
            QPushButton {{ border:none; border-radius:8px; padding:9px 14px;
                           font-weight:700; font-size:12px; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(8)

        title = QLabel("📊 Statistik Produksi")
        title.setStyleSheet(f"color:{COL_HEADING}; font-size:16px; font-weight:800;")
        lay.addWidget(title)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(8)
        lay.addLayout(self.grid)
        self._rows = {}

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color:{COL_MUTED}; font-size:11px; font-weight:600;")
        self.status_lbl.setWordWrap(True)
        lay.addSpacing(4)
        lay.addWidget(self.status_lbl)

        row = QHBoxLayout()
        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setStyleSheet(
            f"background:{COL_SURFACE_ALT}; color:{COL_HEADING}; border:1px solid {COL_BORDER};")
        btn_refresh.clicked.connect(self.refresh)
        btn_export = QPushButton("⬇ Export ke USB")
        btn_export.setStyleSheet(f"background:{COL_ACCENT}; color:white;")
        btn_export.clicked.connect(self._export)
        btn_close = QPushButton("Tutup")
        btn_close.setStyleSheet(
            f"background:{COL_SURFACE_ALT}; color:{COL_HEADING}; border:1px solid {COL_BORDER};")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_refresh)
        row.addWidget(btn_export)
        row.addStretch(1)
        row.addWidget(btn_close)
        lay.addLayout(row)

        self.refresh()

    def _stat_row(self, r, label, value, big=False):
        name = QLabel(label)
        name.setStyleSheet(f"color:{COL_MUTED}; font-size:12px; font-weight:600;")
        val = QLabel(value)
        size = 22 if big else 14
        val.setStyleSheet(f"color:{COL_HEADING}; font-size:{size}px; font-weight:800;")
        self.grid.addWidget(name, r, 0)
        self.grid.addWidget(val, r, 1)

    def refresh(self):
        # Clear grid
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        s = self.master.logger.read_stats()
        grades = s["grades"]
        a, b = grades.get("A", 0), grades.get("B", 0)
        r = grades.get("R", 0) + grades.get("REJECT", 0)
        other = s["total"] - a - b - r
        self._stat_row(0, "Hari ini", str(s["today"]), big=True)
        self._stat_row(1, "Total unit", str(s["total"]), big=True)
        self._stat_row(2, "Grade A", str(a))
        self._stat_row(3, "Grade B", str(b))
        self._stat_row(4, "Reject (R)", str(r))
        if other:
            self._stat_row(5, "Lainnya", str(other))
        self._stat_row(6, "Rata-rata siklus", f"{s['avg_cycle_s']} s")
        self._stat_row(7, "Terakhir", s["last_ts"] or "—")
        self.status_lbl.setText("")

    def _export(self):
        import shutil, glob, getpass
        # Cari mountpoint USB: /media/<user>/* atau /run/media/<user>/*
        user = getpass.getuser()
        mounts = (glob.glob(f"/media/{user}/*") + glob.glob("/media/*/*")
                  + glob.glob(f"/run/media/{user}/*"))
        mounts = [m for m in mounts if os.path.isdir(m)]
        if not mounts:
            self.status_lbl.setText("⚠ Tidak ada USB terdeteksi (/media). Colok flashdisk lalu Refresh.")
            return
        dest_root = os.path.join(mounts[0], "RECELL-AI-export")
        try:
            os.makedirs(dest_root, exist_ok=True)
            src = self.master.logger.output_dir
            n = 0
            for f in glob.glob(os.path.join(src, "*.csv")):
                shutil.copy2(f, dest_root); n += 1
            # Passport PDFs (kalau ada)
            pdf_dir = getattr(self.master.passport_gen, "output_dir", None)
            if pdf_dir and os.path.isdir(pdf_dir):
                pdest = os.path.join(dest_root, "passports")
                os.makedirs(pdest, exist_ok=True)
                for f in glob.glob(os.path.join(pdf_dir, "*.pdf")):
                    shutil.copy2(f, pdest); n += 1
            self.master.logger.log_event("EXPORT_USB", dest_root)
            self.status_lbl.setText(f"✓ {n} file ter-export ke {dest_root}")
        except Exception as e:
            self.status_lbl.setText(f"⚠ Export gagal: {e}")


# ----- BRIDGE ---------------------------------------------------------------
class UIBridge(QObject):
    frame_signal = pyqtSignal(np.ndarray)
    telemetry_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    discharge_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(dict)
    diag_signal = pyqtSignal(dict)             # live diagnostic snapshot (panel)
    init_done_signal = pyqtSignal()
    passport_signal = pyqtSignal(str, str)   # (pdf_path, grade)


# ----- MAIN WINDOW ----------------------------------------------------------
class RecellDashboard(QMainWindow):
    def __init__(self, simulate=False, mock_ai=False):
        super().__init__()
        self.setWindowTitle("RECELL-AI | Intelligent Battery Grading Terminal")
        self.setMinimumSize(900, 600)
        self.resize(1366, 768)
        self.setStyleSheet(GLOBAL_QSS)

        self.cycle_in_progress = False
        self.master = None          # set oleh _init_master_bg setelah load selesai
        self._session_count = 0
        self.discharge_t = []
        self.discharge_v = []
        self.discharge_i = []

        self._build_ui()

        self.bridge = UIBridge()
        self.bridge.frame_signal.connect(self.update_camera_frame)
        self.bridge.telemetry_signal.connect(self.update_telemetry)
        self.bridge.log_signal.connect(self.log_msg)
        self.bridge.progress_signal.connect(self.update_progress)
        self.bridge.discharge_signal.connect(self.update_discharge)
        self.bridge.status_signal.connect(self.update_status)
        self.bridge.diag_signal.connect(self._on_diag)
        self.bridge.init_done_signal.connect(self._on_master_ready)
        self._calib_dialog = None
        self.bridge.passport_signal.connect(self._on_passport_ready)

        self._init_master(simulate, mock_ai)

    # ----- UI CONSTRUCTION --------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        outer.addLayout(self._build_header())
        outer.addLayout(self._build_progress_row())
        outer.addLayout(self._build_main_grid(), stretch=1)

    def _build_header(self):
        bar = QHBoxLayout()
        bar.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("RECELL-AI")
        title.setStyleSheet(
            f"color:{COL_HEADING}; font-size:26px; font-weight:900; letter-spacing:2.5px;"
        )
        sub = QLabel("INTELLIGENT BATTERY GRADING TERMINAL  ·  KIWIE 2026")
        sub.setStyleSheet(
            f"color:{COL_MUTED}; font-size:11px; letter-spacing:2px; font-weight:600;"
        )
        title_box.addWidget(title)
        title_box.addWidget(sub)
        bar.addLayout(title_box)
        bar.addStretch(1)

        # Counter baterai sesi ini
        counter_box = QVBoxLayout()
        counter_box.setSpacing(0)
        counter_box.setAlignment(Qt.AlignCenter)
        self.counter_lbl = QLabel("0")
        self.counter_lbl.setStyleSheet(
            f"color:{COL_ACCENT_TXT}; font-size:22px; font-weight:900;"
        )
        self.counter_lbl.setAlignment(Qt.AlignCenter)
        counter_sub = QLabel("BATERAI SESI INI")
        counter_sub.setStyleSheet(
            f"color:{COL_MUTED}; font-size:9px; letter-spacing:1.5px; font-weight:700;"
        )
        counter_sub.setAlignment(Qt.AlignCenter)
        counter_box.addWidget(self.counter_lbl)
        counter_box.addWidget(counter_sub)
        bar.addLayout(counter_box)

        # Jam digital
        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        clock_box.setAlignment(Qt.AlignCenter)
        self.clock_lbl = QLabel(time.strftime("%H:%M:%S"))
        self.clock_lbl.setStyleSheet(
            f"color:{COL_HEADING}; font-size:20px; font-weight:800; letter-spacing:1px;"
        )
        self.clock_lbl.setAlignment(Qt.AlignCenter)
        clock_date = QLabel(time.strftime("%d %b %Y"))
        clock_date.setStyleSheet(
            f"color:{COL_MUTED}; font-size:9px; letter-spacing:1px; font-weight:600;"
        )
        clock_date.setAlignment(Qt.AlignCenter)
        clock_box.addWidget(self.clock_lbl)
        clock_box.addWidget(clock_date)
        bar.addLayout(clock_box)

        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(lambda: self.clock_lbl.setText(time.strftime("%H:%M:%S")))
        self._clock_timer.start(1000)

        self.pill_camera = StatusPill("CAMERA", clickable=True)
        self.pill_camera.clicked.connect(self._restart_camera)
        self.pill_serial = StatusPill("STM32", clickable=True)
        self.pill_serial.clicked.connect(self._open_serial_config)
        self.pill_yolo   = StatusPill("YOLO")
        self.pill_xgb    = StatusPill("XGB")
        for p in (self.pill_camera, self.pill_serial, self.pill_yolo, self.pill_xgb):
            bar.addWidget(p)

        return bar

    def _build_progress_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("STANDBY  ·  %p%")
        row.addWidget(self.progress_bar, stretch=1)

        self.stage_lbl = QLabel("Stage: idle")
        self.stage_lbl.setStyleSheet(
            f"color:{COL_HEADING}; font-size:12px; font-weight:700;"
        )
        row.addWidget(self.stage_lbl)
        return row

    def _build_main_grid(self):
        grid = QHBoxLayout()
        grid.setSpacing(12)
        grid.addLayout(self._build_left_column(), stretch=5)
        grid.addLayout(self._build_right_column(), stretch=7)
        return grid

    def _build_left_column(self):
        col = QVBoxLayout()
        col.setSpacing(12)

        cam_card = Card(title="Edge AI Vision  ·  YOLOv8n", accent=COL_PURPLE)
        self.cam_label = QLabel("INITIALIZING CAMERA…")
        self.cam_label.setAlignment(Qt.AlignCenter)
        self.cam_label.setMinimumSize(320, 200)
        self.cam_label.setStyleSheet(
            f"background-color:{COL_SURFACE_ALT}; color:{COL_MUTED}; "
            f"border:1px dashed {COL_BORDER}; border-radius:8px; font-size:13px;"
            f"font-weight:600;"
        )
        self.cam_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cam_card.body.addWidget(self.cam_label, stretch=1)

        # Vision score + defect chips
        info_row = QHBoxLayout()
        info_row.setSpacing(10)
        self.vision_score_lbl = QLabel("Vision Score:  --")
        self.vision_score_lbl.setStyleSheet(
            f"color:{COL_HEADING}; font-size:13px; font-weight:700;"
        )
        info_row.addWidget(self.vision_score_lbl)
        info_row.addStretch(1)
        self.defects_container = QHBoxLayout()
        self.defects_container.setSpacing(6)
        info_row.addLayout(self.defects_container)
        cam_card.body.addLayout(info_row)
        col.addWidget(cam_card, stretch=1)

        # Control buttons
        ctrl_card = Card(title="Conveyor Control", accent=COL_INFO)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_start = QPushButton("▶  START AUTO CYCLE")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setMinimumHeight(46)
        self.btn_start.clicked.connect(self.trigger_cycle)

        self.btn_stop = QPushButton("■  EMERGENCY STOP")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setMinimumHeight(46)
        self.btn_stop.clicked.connect(self.trigger_stop)

        self.btn_calib = QPushButton("⚙  KALIBRASI")
        self.btn_calib.setMinimumHeight(46)
        self.btn_calib.setToolTip("Buka panel kalibrasi / setup (F12)")
        self.btn_calib.setStyleSheet(
            f"background-color:{COL_SURFACE}; color:{COL_HEADING};"
            f"border:1px solid {COL_BORDER};"
        )
        self.btn_calib.clicked.connect(self.open_calibration)

        self.btn_stats = QPushButton("📊  STATISTIK")
        self.btn_stats.setMinimumHeight(46)
        self.btn_stats.setToolTip("Statistik produksi + export log")
        self.btn_stats.setStyleSheet(
            f"background-color:{COL_SURFACE}; color:{COL_HEADING};"
            f"border:1px solid {COL_BORDER};"
        )
        self.btn_stats.clicked.connect(self.open_stats)

        btn_row.addWidget(self.btn_start, stretch=2)
        btn_row.addWidget(self.btn_stop, stretch=1)
        btn_row.addWidget(self.btn_calib, stretch=1)
        btn_row.addWidget(self.btn_stats, stretch=1)
        ctrl_card.body.addLayout(btn_row)

        self.calib_lbl = QLabel("Kalibrasi:  —")
        self.calib_lbl.setStyleSheet(f"color:{COL_MUTED}; font-size:11px; font-weight:600;")
        ctrl_card.body.addWidget(self.calib_lbl)

        col.addWidget(ctrl_card)

        return col

    def _build_right_column(self):
        col = QVBoxLayout()
        col.setSpacing(12)

        # Telemetry cards row (3 metrics)
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)
        self.card_v = MetricCard("Voltage (Loaded)", "V", accent=COL_ACCENT, value_color=COL_ACCENT_TXT)
        self.card_i = MetricCard("Load Current", "A", accent=COL_INFO, value_color=COL_INFO_TXT)
        self.card_soh = MetricCard("State of Health", "%", accent=COL_WARN, value_color=COL_WARN_TXT)
        metrics_row.addWidget(self.card_v)
        metrics_row.addWidget(self.card_i)
        metrics_row.addWidget(self.card_soh)
        col.addLayout(metrics_row)

        # Grade card (hero)
        self.grade_card = GradeCard()
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(24); glow.setOffset(0, 4)
        glow.setColor(QColor(15, 23, 42, 35))
        self.grade_card.setGraphicsEffect(glow)
        col.addWidget(self.grade_card)

        # Baris aksi pasca-siklus: override grade + buka passport
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        override_lbl = QLabel("Override:")
        override_lbl.setStyleSheet(
            f"color:{COL_MUTED}; font-size:11px; font-weight:700; letter-spacing:0.5px;"
        )
        action_row.addWidget(override_lbl)

        for grade, color in [("A", COL_ACCENT), ("B", COL_WARN), ("R", COL_ERROR)]:
            btn = QPushButton(f"  {grade}  ")
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                f"background:{color}; color:white; border-radius:8px;"
                f"font-size:13px; font-weight:900; padding:0 10px;"
            )
            btn.clicked.connect(lambda _, g=grade: self._override_grade(g))
            setattr(self, f"btn_override_{grade}", btn)
            btn.setEnabled(False)
            action_row.addWidget(btn)

        action_row.addStretch(1)

        self.btn_passport = QPushButton("📄  Buka Passport")
        self.btn_passport.setFixedHeight(32)
        self.btn_passport.setStyleSheet(
            f"background:{COL_INFO}; color:white; border-radius:8px;"
            f"font-size:12px; font-weight:700;"
        )
        self.btn_passport.setEnabled(False)
        self.btn_passport.clicked.connect(self._open_passport)
        self._last_pdf_path = None
        action_row.addWidget(self.btn_passport)
        col.addLayout(action_row)

        # Discharge plot
        plot_card = Card(title="Constant Current Load · Discharge Curve",
                         accent=COL_ACCENT)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(COL_SURFACE)
        self.plot_widget.setLabel('left', 'Voltage (V)', color=COL_ACCENT, size='10pt')
        self.plot_widget.setLabel('bottom', 'Time (ms)', color=COL_MUTED, size='10pt')
        for ax in ("left", "bottom"):
            axis = self.plot_widget.getAxis(ax)
            axis.setPen(pg.mkPen(COL_BORDER))
            axis.setTextPen(pg.mkPen(COL_HEADING))
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.addLegend(offset=(10, 8), labelTextColor=COL_HEADING,
                                   brush=pg.mkBrush('#FFFFFFE6'),
                                   pen=pg.mkPen(COL_BORDER))
        self.plot_widget.setMinimumHeight(100)
        self.curve_v = self.plot_widget.plot(
            pen=pg.mkPen(COL_ACCENT, width=2.6), name="Voltage (V)")
        self.curve_i = self.plot_widget.plot(
            pen=pg.mkPen(COL_INFO, width=2.0, style=Qt.DashLine), name="Current (A)")
        plot_card.body.addWidget(self.plot_widget)
        col.addWidget(plot_card, stretch=2)

        # Log terminal
        log_card = Card(title="System Terminal", accent=COL_MUTED)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("JetBrains Mono", 9))
        self.log_console.setMinimumHeight(80)
        log_card.body.addWidget(self.log_console)
        col.addWidget(log_card, stretch=2)

        return col

    # ----- MASTER WIRING ----------------------------------------------------
    def _init_master(self, simulate, mock_ai):
        """Tampilkan UI langsung; load YOLO + hardware di background thread."""
        self.btn_start.setEnabled(False)
        self.grade_card.set_state("MEMUAT…", COL_INFO_TXT,
                                  "Memuat model AI & menginisialisasi hardware",
                                  bg="#EFF6FF", border="#BFDBFE")
        self.update_progress(0, "Memuat model AI…")
        self.log_msg("[BOOT] Memulai RECELL-AI Core Engine (background)…")

        callbacks = {
            'on_frame':            self.bridge.frame_signal.emit,
            'on_telemetry':        self.bridge.telemetry_signal.emit,
            'on_log':              self.bridge.log_signal.emit,
            'on_discharge_sample': self.bridge.discharge_signal.emit,
            'on_status':           self.bridge.status_signal.emit,
            'on_passport':         self.bridge.passport_signal.emit,
            'on_diag':             self.bridge.diag_signal.emit,
        }

        def _bg():
            master = RecellMaster(simulate=simulate, mock_ai=mock_ai,
                                  ui_callbacks=callbacks)
            self.master = master
            self.master_thread = threading.Thread(target=master.run, daemon=True)
            self.master_thread.start()
            self.bridge.init_done_signal.emit()

        threading.Thread(target=_bg, daemon=True).start()

    def _on_master_ready(self):
        """Dipanggil di main thread setelah RecellMaster selesai diinisialisasi."""
        self.update_status(dict(self.master.status))
        self._refresh_calib_label()
        self.grade_card.set_grade("STANDBY")
        self.update_progress(0, "Standby")
        self.btn_start.setEnabled(True)
        self.log_msg("[BOOT] Sistem siap.")

    # ----- ACTIONS ----------------------------------------------------------
    def _restart_camera(self):
        if self.master is None:
            return
        self.master.restart_camera()

    def _override_grade(self, grade):
        if self.master is None:
            return
        prev = self.master.grade_decision
        self.master.override_grade(grade)
        self.grade_card.set_grade(grade)
        # Audit trail: operator menimpa keputusan AI.
        bid = self.master.current_battery_id or "?"
        self.master.logger.log_event("GRADE_OVERRIDE", f"{bid}: {prev}->{grade}")

    def _open_passport(self):
        if self._last_pdf_path and Path(self._last_pdf_path).exists():
            subprocess.Popen(['xdg-open', self._last_pdf_path])
        else:
            self.log_msg("[!] File passport tidak ditemukan.")

    def _on_passport_ready(self, pdf_path, grade):
        self._last_pdf_path = pdf_path
        self.btn_passport.setEnabled(bool(pdf_path))
        for g in ("A", "B", "R"):
            getattr(self, f"btn_override_{g}").setEnabled(True)

    def _exec_dialog_on_top(self, dlg):
        """Tampilkan dialog modal DI ATAS window utama yang fullscreen.

        Bug lapangan: window fullscreen (mutter menumpuk _NET_WM_STATE_FULLSCREEN
        di atas window normal) menimbun dialog modal → dialog tak terlihat tapi
        tetap merebut semua input → UI tampak beku/tak bisa dipencet. Solusi:
        non-fullscreen-kan main window selama dialog terbuka, paksa dialog di
        atas + fokus, lalu kembalikan fullscreen."""
        dlg.setWindowFlags(dlg.windowFlags() | Qt.Dialog | Qt.WindowStaysOnTopHint)
        was_fs = self.isFullScreen()
        if was_fs:
            self.showNormal()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        try:
            return dlg.exec_()
        finally:
            if was_fs:
                self.showFullScreen()

    def _open_serial_config(self):
        if self.master is None:
            return
        dlg = SerialConfigDialog(self.master, parent=self)
        self._exec_dialog_on_top(dlg)
        self.update_status(dict(self.master.status))

    def open_calibration(self):
        if self.master is None:
            return
        dlg = CalibrationDialog(self.master, parent=self)
        self._calib_dialog = dlg
        self.master.start_diag()          # firmware mulai stream sensor live
        try:
            self._exec_dialog_on_top(dlg)
        finally:
            self.master.stop_diag()
            self._calib_dialog = None
        self._refresh_calib_label()

    def _on_diag(self, data):
        """Forward live diagnostic snapshot to the calibration dialog if open."""
        dlg = self._calib_dialog
        if dlg is not None:
            dlg.update_monitor(data)

    def open_stats(self):
        if self.master is None:
            return
        self._exec_dialog_on_top(StatsDialog(self.master, parent=self))

    def _refresh_calib_label(self):
        if self.master is None:
            return
        c = self.master.calibration
        self.calib_lbl.setText(
            f"Kalibrasi:  speed {c.get('conveyor_speed')}  ·  pulse {c.get('step_pulse_us')} µs")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F12:
            self.open_calibration()
        else:
            super().keyPressEvent(event)

    def trigger_cycle(self):
        if self.master is None:
            self.log_msg("[!] Sistem masih memuat, harap tunggu.")
            return
        if self.cycle_in_progress:
            self.log_msg("[!] Cycle already in progress.")
            return
        # Cegah dua thread siklus jalan bersamaan kalau thread lama (mis. setelah
        # Emergency Stop) belum selesai unwinding — keduanya akan rebutan serial.
        if getattr(self, "_cycle_thread", None) and self._cycle_thread.is_alive():
            self.log_msg("[!] Siklus sebelumnya masih berhenti — tunggu sebentar lalu START lagi.")
            return
        # Interlock: jangan mulai siklus kalau STM32 offline/simulasi — perintah
        # akan tertelan & konveyor tak terkendali. "stale" (heartbeat sempat
        # hilang) tetap diizinkan: perintah START akan menyegarkan status, dan
        # timeout siklus menangani bila board memang hang.
        if self.master.status.get("serial") in ("offline", "sim"):
            self.log_msg("[!] START ditolak: STM32 tidak online (cek koneksi serial).")
            return
        self.cycle_in_progress = True
        self.btn_start.setEnabled(False)

        # Reset state for new cycle
        self.discharge_t.clear()
        self.discharge_v.clear()
        self.discharge_i.clear()
        self.curve_v.setData([], [])
        self.curve_i.setData([], [])
        self._clear_defects()
        self._last_pdf_path = None
        self.btn_passport.setEnabled(False)
        for g in ("A", "B", "R"):
            getattr(self, f"btn_override_{g}").setEnabled(False)

        self.grade_card.set_state("TESTING…", COL_WARN_TXT,
                                  "Running Electrochemical Analysis",
                                  bg="#FFFBEB", border="#FDE68A")

        self.update_progress(5, "Starting cycle…")
        self._cycle_thread = threading.Thread(target=self._run_cycle_wrapper, daemon=True)
        self._cycle_thread.start()

    def _run_cycle_wrapper(self):
        try:
            self.master.run_automated_cycle()
            self._session_count += 1
            QTimer.singleShot(0, lambda: self.counter_lbl.setText(str(self._session_count)))
        finally:
            self.cycle_in_progress = False
            # Jangan klaim "complete" kalau siklus di-abort (Emergency Stop).
            if not self.master.abort_cycle:
                self.bridge.progress_signal.emit(100, "Cycle complete")
            QTimer.singleShot(0, lambda: self.btn_start.setEnabled(True))

    def trigger_stop(self):
        if self.master is None:
            return
        self.log_msg(">>> EMERGENCY STOP INITIATED <<<")
        self.master.abort_cycle = True
        self.master.send_command("STOP_CONVEYOR")
        self.master.wait_flag = False
        self.update_progress(0, "Aborted")
        self.grade_card.set_state("ABORTED", COL_ERROR_TXT, "Cycle Interrupted",
                                  bg="#FEF2F2", border="#FECACA")
        # E-stop otoritatif: kembalikan UI ke kondisi bisa-START sekarang juga,
        # jangan menunggu thread siklus lama unwinding lewat finally-nya. Guard
        # is_alive di trigger_cycle mencegah dua siklus jalan bersamaan.
        self.cycle_in_progress = False
        self.btn_start.setEnabled(True)

    # ----- SLOTS ------------------------------------------------------------
    def log_msg(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.log_console.appendPlainText(f"[{ts}]  {msg}")
        sb = self.log_console.verticalScrollBar()
        sb.setValue(sb.maximum())

        # Map known log lines to progress stage updates
        if "Evaluating Vision" in msg:
            self.update_progress(20, "Vision analysis")
        elif "Moving to Sensor" in msg:
            self.update_progress(40, "Conveyor → PROX 1")
        elif "Pushing Sensor" in msg or "Measuring" in msg:
            self.update_progress(60, "Constant-current load test")
        elif "Grading Decision" in msg:
            self.update_progress(85, "Grading…")
        elif "Passport Generated" in msg:
            self.update_progress(95, "Passport PDF")
        elif "Cycle Complete" in msg:
            self.update_progress(100, "Done")

    def update_progress(self, val, stage=None):
        self.progress_bar.setValue(val)
        if stage is not None:
            self.progress_bar.setFormat(f"{stage.upper()}  ·  %p%")
            self.stage_lbl.setText(f"Stage: {stage}")

    def update_telemetry(self, data):
        v = data.get('volt', 0) or 0
        i = data.get('curr', 0) or 0
        soh = data.get('soh', 0) or 0
        vs = data.get('vision_score', None)
        defects = data.get('defects', [])

        self.card_v.set_value(f"{v:.2f}", subtitle=f"Loaded under {i:.2f} A")
        self.card_i.set_value(f"{i:.2f}", subtitle="Constant-current load")
        # SOH band subtitle
        if soh >= 80:
            sub = "Excellent · Reuse"
        elif soh >= 60:
            sub = "Acceptable · Refurbish"
        else:
            sub = "Degraded · Recycle"
        self.card_soh.set_value(f"{soh:.1f}", subtitle=sub)

        if vs is not None:
            self.vision_score_lbl.setText(f"Vision Score:  {vs:.2f} / 1.00")
        self._render_defects(defects)

        grade = data.get('grade', '--')
        if grade in GRADE_COLORS:
            self.grade_card.set_grade(grade)

    def update_discharge(self, sample):
        t = sample.get('t_ms', 0)
        v = sample.get('voltage', 0)
        i = sample.get('current', 0)
        self.discharge_t.append(t)
        self.discharge_v.append(v)
        self.discharge_i.append(i)
        # Cap buffer so very long curves don't bloat memory
        if len(self.discharge_t) > 4000:
            self.discharge_t = self.discharge_t[-4000:]
            self.discharge_v = self.discharge_v[-4000:]
            self.discharge_i = self.discharge_i[-4000:]
        self.curve_v.setData(self.discharge_t, self.discharge_v)
        self.curve_i.setData(self.discharge_t, self.discharge_i)

    def update_status(self, status):
        self.pill_camera.set_state(status.get("camera", "offline"))
        self.pill_serial.set_state(status.get("serial", "offline"))
        self.pill_yolo.set_state(status.get("yolo", "offline"))
        self.pill_xgb.set_state(status.get("xgb", "offline"))

        # Camera viewport placeholder reflects the current camera state.
        cam_state = status.get("camera", "offline")
        if cam_state == "online":
            return  # actual frames will overwrite the placeholder
        if self.cam_label.pixmap() is not None:
            return  # already showing a real frame
        placeholders = {
            "mock":    ("VISION MOCK MODE",        "no live camera input"),
            "offline": ("NO CAMERA DETECTED",      "running headless"),
        }
        title, sub = placeholders.get(cam_state, ("INITIALIZING CAMERA…", ""))
        self.cam_label.setText(f"{title}\n\n{sub}" if sub else title)
        self.cam_label.setStyleSheet(
            f"background-color:{COL_SURFACE_ALT}; color:{COL_MUTED};"
            f"border:1px dashed {COL_BORDER}; border-radius:8px;"
            f"font-size:13px; font-weight:600;"
        )

    def update_camera_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        self.cam_label.setPixmap(
            pixmap.scaled(self.cam_label.width(), self.cam_label.height(),
                          Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ----- HELPERS ----------------------------------------------------------
    def _clear_defects(self):
        while self.defects_container.count():
            item = self.defects_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render_defects(self, defects):
        self._clear_defects()
        if not defects:
            placeholder = QLabel("No defects detected")
            placeholder.setStyleSheet(
                f"color:{COL_MUTED}; font-size:11px; font-weight:600;"
            )
            self.defects_container.addWidget(placeholder)
            return
        palette = {
            "KARAT": COL_WARN,
            "SOBEK": COL_ERROR,
            "SEHAT": COL_ACCENT,
        }
        for label in defects:
            chip = DefectChip(label, color=palette.get(label, COL_PURPLE))
            self.defects_container.addWidget(chip)

    def closeEvent(self, event):
        if self.master is not None:
            self.master.running = False
        event.accept()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RECELL-AI Dashboard")
    parser.add_argument('--sim', action='store_true', help='Run without STM32 connected')
    parser.add_argument('--mock-ai', action='store_true', help='Run without YOLO/Camera')
    parser.add_argument('--fullscreen', action='store_true', help='Launch in fullscreen mode')
    parser.add_argument('--smoke-test', metavar='OUTDIR',
                        help='Auto-run one cycle and save screenshots to OUTDIR, then quit')
    args, unknown = parser.parse_known_args()

    sys_argv = [sys.argv[0]] + unknown
    app = QApplication(sys_argv)
    app.setStyle("Fusion")

    window = RecellDashboard(simulate=args.sim, mock_ai=args.mock_ai)
    if args.fullscreen:
        screen_geo = app.primaryScreen().geometry()
        # Frameless seukuran layar, TAPI tetap dikelola WM. JANGAN pakai
        # X11BypassWindowManagerHint: itu menggambar window langsung di atas
        # segalanya & melewati WM, sehingga dialog modal (Kalibrasi/Serial) yang
        # dikelola WM tertimbun di belakang dan mengunci seluruh input.
        window.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        window.setGeometry(screen_geo)
    window.show()

    if args.smoke_test:
        out = Path(args.smoke_test)
        out.mkdir(parents=True, exist_ok=True)

        def _grab(name):
            pix = window.grab()
            path = out / name
            pix.save(str(path), "PNG")
            print(f"[SMOKE] saved {path}")

        # initial state shot
        QTimer.singleShot(1500, lambda: _grab("01_initial.png"))
        # kick off a cycle
        QTimer.singleShot(2000, window.trigger_cycle)
        # mid-cycle (during discharge plot)
        QTimer.singleShot(3500, lambda: _grab("02_running.png"))
        # post-cycle (grade decided)
        QTimer.singleShot(7000, lambda: _grab("03_complete.png"))
        # quit
        QTimer.singleShot(8000, app.quit)

    sys.exit(app.exec_())
