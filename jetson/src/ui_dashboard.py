"""RECELL-AI Industrial HMI Dashboard.

Tier-1 PyQt5 dashboard that wraps RecellMaster. Designed for the Jetson Orin
Nano's display but works on any desktop Linux with Qt.
"""

import sys
import cv2
import numpy as np
import threading
import time
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QFrame, QPlainTextEdit, QProgressBar, QSizePolicy, QGraphicsDropShadowEffect,
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
COL_ACCENT      = "#10B981"   # emerald 500 (voltage / Grade A)
COL_INFO        = "#3B82F6"   # blue 500 (current / info)
COL_WARN        = "#F59E0B"   # amber 500 (SOH / testing)
COL_PURPLE      = "#8B5CF6"   # violet 500 (vision / accent variety)
COL_ERROR       = "#EF4444"   # red 500 (reject / stop)
COL_STANDBY     = "#94A3B8"   # slate-400


GRADE_COLORS = {
    # (text color, subtitle, soft bg, border)
    "A": (COL_ACCENT, "Second-Life Compatible", "#ECFDF5", "#A7F3D0"),
    "B": (COL_WARN,   "Refurbish / Limited Use", "#FFFBEB", "#FDE68A"),
    "R": (COL_ERROR,  "Rejected (Recycle)",      "#FEF2F2", "#FECACA"),
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
QPushButton#btnStart:disabled {{ background-color: #D1FAE5; color: #6EE7B7; }}
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
    """A small pill showing a label and a colored dot."""
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet(
            f"background-color:{COL_SURFACE}; border:1px solid {COL_BORDER};"
            f"border-radius:15px;"
        )
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

    def set_state(self, state):
        states = {
            "online":  (COL_ACCENT,   "ONLINE"),
            "sim":     (COL_INFO,     "SIM"),
            "mock":    (COL_WARN,     "MOCK"),
            "rule":    (COL_WARN,     "RULE"),
            "offline": (COL_STANDBY,  "OFFLINE"),
        }
        color, text = states.get(state, states["offline"])
        self.dot.setStyleSheet(f"background-color:{color}; border-radius:5px;")
        self.val.setText(text)
        self.val.setStyleSheet(f"color:{color}; font-size:11px; font-weight:800;")


class MetricCard(Card):
    """A card displaying one big metric value with a unit and subtitle."""
    def __init__(self, title, unit, accent=COL_TEXT, parent=None):
        super().__init__(title=title, accent=accent, parent=parent)
        self.accent = accent
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setAlignment(Qt.AlignBottom)

        self.value_lbl = QLabel("--")
        f = QFont("Inter", 30, QFont.Bold)
        f.setStyleStrategy(QFont.PreferAntialias)
        self.value_lbl.setFont(f)
        self.value_lbl.setStyleSheet(f"color:{accent};")

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


# ----- BRIDGE ---------------------------------------------------------------
class UIBridge(QObject):
    frame_signal = pyqtSignal(np.ndarray)
    telemetry_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    discharge_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(dict)


# ----- MAIN WINDOW ----------------------------------------------------------
class RecellDashboard(QMainWindow):
    def __init__(self, simulate=False, mock_ai=False):
        super().__init__()
        self.setWindowTitle("RECELL-AI | Intelligent Battery Grading Terminal")
        self.setGeometry(40, 40, 1440, 860)
        self.setStyleSheet(GLOBAL_QSS)

        self.cycle_in_progress = False
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

        self.pill_camera = StatusPill("CAMERA")
        self.pill_serial = StatusPill("STM32")
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
        self.cam_label.setMinimumSize(560, 380)
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

        btn_row.addWidget(self.btn_start, stretch=2)
        btn_row.addWidget(self.btn_stop, stretch=1)
        ctrl_card.body.addLayout(btn_row)
        col.addWidget(ctrl_card)

        return col

    def _build_right_column(self):
        col = QVBoxLayout()
        col.setSpacing(12)

        # Telemetry cards row (3 metrics)
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)
        self.card_v = MetricCard("Voltage (Loaded)", "V", accent=COL_ACCENT)
        self.card_i = MetricCard("Load Current", "A", accent=COL_INFO)
        self.card_soh = MetricCard("State of Health", "%", accent=COL_WARN)
        metrics_row.addWidget(self.card_v)
        metrics_row.addWidget(self.card_i)
        metrics_row.addWidget(self.card_soh)
        col.addLayout(metrics_row)

        # Grade card (hero)
        self.grade_card = GradeCard()
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(24); glow.setOffset(0, 4)
        glow.setColor(QColor(15, 23, 42, 35))  # soft slate shadow
        self.grade_card.setGraphicsEffect(glow)
        col.addWidget(self.grade_card)

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
        self.plot_widget.setMinimumHeight(180)
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
        self.log_console.setMinimumHeight(140)
        log_card.body.addWidget(self.log_console)
        col.addWidget(log_card, stretch=2)

        return col

    # ----- MASTER WIRING ----------------------------------------------------
    def _init_master(self, simulate, mock_ai):
        self.log_msg("[BOOT] Initializing RECELL-AI Core Engine...")
        callbacks = {
            'on_frame': self.bridge.frame_signal.emit,
            'on_telemetry': self.bridge.telemetry_signal.emit,
            'on_log': self.bridge.log_signal.emit,
            'on_discharge_sample': self.bridge.discharge_signal.emit,
            'on_status': self.bridge.status_signal.emit,
        }
        self.master = RecellMaster(simulate=simulate, mock_ai=mock_ai, ui_callbacks=callbacks)
        self.master_thread = threading.Thread(target=self.master.run, daemon=True)
        self.master_thread.start()
        # Push initial status to UI now that signals are connected.
        self.update_status(dict(self.master.status))

    # ----- ACTIONS ----------------------------------------------------------
    def trigger_cycle(self):
        if self.cycle_in_progress:
            self.log_msg("[!] Cycle already in progress.")
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

        self.grade_card.set_state("TESTING…", COL_WARN,
                                  "Running Electrochemical Analysis",
                                  bg="#FFFBEB", border="#FDE68A")

        self.update_progress(5, "Starting cycle…")
        threading.Thread(target=self._run_cycle_wrapper, daemon=True).start()

    def _run_cycle_wrapper(self):
        try:
            self.master.run_automated_cycle()
        finally:
            self.cycle_in_progress = False
            # Schedule UI re-enable on main thread via signal
            self.bridge.progress_signal.emit(100, "Cycle complete")
            QTimer.singleShot(0, lambda: self.btn_start.setEnabled(True))

    def trigger_stop(self):
        self.log_msg(">>> EMERGENCY STOP INITIATED <<<")
        self.master.abort_cycle = True
        self.master.send_command("STOP_CONVEYOR")
        self.master.wait_flag = False
        self.update_progress(0, "Aborted")
        self.grade_card.set_state("ABORTED", COL_ERROR, "Cycle Interrupted",
                                  bg="#FEF2F2", border="#FECACA")

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
        self.master.running = False
        event.accept()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RECELL-AI Dashboard")
    parser.add_argument('--sim', action='store_true', help='Run without STM32 connected')
    parser.add_argument('--mock-ai', action='store_true', help='Run without YOLO/Camera')
    parser.add_argument('--smoke-test', metavar='OUTDIR',
                        help='Auto-run one cycle and save screenshots to OUTDIR, then quit')
    args, unknown = parser.parse_known_args()

    sys_argv = [sys.argv[0]] + unknown
    app = QApplication(sys_argv)
    app.setStyle("Fusion")

    window = RecellDashboard(simulate=args.sim, mock_ai=args.mock_ai)
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
