import sys
import cv2
import numpy as np
import threading
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QWidget, QGroupBox, 
                             QPlainTextEdit, QGridLayout, QProgressBar)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QImage, QPixmap
import pyqtgraph as pg  # INDUSTRIAL GRAPHING LIBRARY

# Enable Hardware Acceleration (OpenGL) for ultra-fast plotting on Jetson
try:
    pg.setConfigOptions(useOpenGL=True)
except Exception:
    pass # Fallback to standard rendering if OpenGL fails on specific Jetson setups
pg.setConfigOptions(antialias=True)

# Import core master logic
from main import RecellMaster

class UIBridge(QObject):
    """Bridge for safely passing thread data to PyQt GUI main thread."""
    frame_signal = pyqtSignal(np.ndarray)
    telemetry_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

class RecellDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RECELL-AI | Tier-1 Industrial HMI")
        self.setGeometry(50, 50, 1280, 720)
        
        # Advanced Industrial Dark Theme
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; color: #E0E0E0; }
            QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #3A3A3A; border-radius: 5px; margin-top: 2ex; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; color: #00E676; }
            QLabel { color: #FFFFFF; }
            QPushButton { border-radius: 4px; font-weight: bold; }
            QPlainTextEdit { background-color: #0A0A0A; color: #00FF00; border: 1px solid #333; }
            QProgressBar { border: 1px solid #555; border-radius: 5px; text-align: center; font-weight: bold; color: white; background-color: #222; }
            QProgressBar::chunk { background-color: #00E676; width: 10px; margin: 1px; }
        """)

        # Plot Data Buffers
        self.time_data = []
        self.volt_data = []
        self.curr_data = []
        self.start_time = time.time()

        # Set up UI Components
        self.initUI()
        
        # Bridge for thread-safe UI updates
        self.bridge = UIBridge()
        self.bridge.frame_signal.connect(self.update_camera_frame)
        self.bridge.telemetry_signal.connect(self.update_telemetry)
        self.bridge.log_signal.connect(self.log_msg)
        self.bridge.progress_signal.connect(self.update_progress)

        # Initialize Master Controller in background
        self.init_master()

    def init_master(self):
        self.log_msg("[BOOT] Initializing RECELL-AI Core Engine...")
        callbacks = {
            'on_frame': self.bridge.frame_signal.emit,
            'on_telemetry': self.bridge.telemetry_signal.emit,
            'on_log': self.bridge.log_signal.emit,
            'on_progress': self.bridge.progress_signal.emit
        }
        
        # NOTE: Change simulate=False when hardware is connected
        self.master = RecellMaster(simulate=True, mock_ai=True, ui_callbacks=callbacks)
        
        # Inject progress reporting into master's run_automated_cycle
        original_run = self.master.run_automated_cycle
        def hooked_run():
            self.master.ui_callbacks.get('on_progress', lambda x: None)(10)
            original_run()
            self.master.ui_callbacks.get('on_progress', lambda x: None)(100)
            
        self.master.run_automated_cycle = hooked_run

        self.master_thread = threading.Thread(target=self.master.run, daemon=True)
        self.master_thread.start()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- HEADER ---
        header_label = QLabel("RECELL-AI INTELLIGENT GRADING TERMINAL")
        header_label.setFont(QFont("Segoe UI", 22, QFont.Bold))
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setStyleSheet("color: #00E676; padding: 10px; background-color: #1A1A1A; border-radius: 5px;")
        main_layout.addWidget(header_label)

        # CYCLE PROGRESS BAR
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        main_layout.addWidget(self.progress_bar)

        # --- CONTENT LAYOUT ---
        content_layout = QHBoxLayout()

        # LEFT COLUMN (Camera & Controls)
        left_panel = QVBoxLayout()
        
        # Camera Group
        cam_group = QGroupBox("EDGE AI VISION (YOLOv8n)")
        cam_layout = QVBoxLayout(cam_group)
        self.cam_label = QLabel("INITIALIZING CAMERA...")
        self.cam_label.setAlignment(Qt.AlignCenter)
        self.cam_label.setStyleSheet("background-color: #000000; border: 2px solid #555;")
        self.cam_label.setFixedSize(640, 480)
        cam_layout.addWidget(self.cam_label)
        left_panel.addWidget(cam_group)

        # Control Buttons
        ctrl_layout = QHBoxLayout()
        btn_start = QPushButton("▶ START AUTO CYCLE")
        btn_start.setStyleSheet("background-color: #00C853; color: black; padding: 15px; font-size: 14px;")
        btn_start.clicked.connect(self.trigger_cycle)
        
        btn_stop = QPushButton("⏹ EMERGENCY STOP")
        btn_stop.setStyleSheet("background-color: #D50000; color: white; padding: 15px; font-size: 14px;")
        btn_stop.clicked.connect(self.trigger_stop)

        ctrl_layout.addWidget(btn_start)
        ctrl_layout.addWidget(btn_stop)
        left_panel.addLayout(ctrl_layout)
        content_layout.addLayout(left_panel, stretch=2)

        # RIGHT COLUMN (Graphs & Telemetry)
        right_panel = QVBoxLayout()

        # Live Graphs (PyQtGraph)
        graph_group = QGroupBox("CONSTANT CURRENT LOAD TEST")
        graph_layout = QVBoxLayout(graph_group)
        pg.setConfigOption('background', '#0A0A0A')
        pg.setConfigOption('foreground', 'd')
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        self.curve_v = self.plot_widget.plot(pen=pg.mkPen('#00E676', width=2), name="Voltage (V)")
        self.curve_i = self.plot_widget.plot(pen=pg.mkPen('#29B6F6', width=2), name="Current (A)")
        graph_layout.addWidget(self.plot_widget)
        right_panel.addWidget(graph_group, stretch=2)

        # Status & Grading
        stat_group = QGroupBox("FINAL GRADING RESULT")
        stat_layout = QGridLayout(stat_group)
        
        lbl_v_title = QLabel("Voltage:")
        self.lbl_volt = QLabel("0.00 V")
        self.lbl_volt.setFont(QFont("Consolas", 18, QFont.Bold))
        
        lbl_i_title = QLabel("Current:")
        self.lbl_curr = QLabel("0.00 A")
        self.lbl_curr.setFont(QFont("Consolas", 18, QFont.Bold))

        lbl_soh_title = QLabel("Health (SOH):")
        self.lbl_soh = QLabel("0.0 %")
        self.lbl_soh.setFont(QFont("Consolas", 18, QFont.Bold))

        self.lbl_grade = QLabel("STANDBY")
        self.lbl_grade.setFont(QFont("Arial", 28, QFont.Bold))
        self.lbl_grade.setAlignment(Qt.AlignCenter)
        self.lbl_grade.setStyleSheet("color: #757575; background: #222; padding: 10px; border-radius: 5px;")

        stat_layout.addWidget(lbl_v_title, 0, 0)
        stat_layout.addWidget(self.lbl_volt, 0, 1)
        stat_layout.addWidget(lbl_i_title, 1, 0)
        stat_layout.addWidget(self.lbl_curr, 1, 1)
        stat_layout.addWidget(lbl_soh_title, 2, 0)
        stat_layout.addWidget(self.lbl_soh, 2, 1)
        stat_layout.addWidget(self.lbl_grade, 0, 2, 3, 1) # Span 3 rows
        right_panel.addWidget(stat_group, stretch=1)

        # Log Terminal
        log_group = QGroupBox("SYSTEM TERMINAL")
        log_layout = QVBoxLayout(log_group)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_console)
        right_panel.addWidget(log_group, stretch=1)

        content_layout.addLayout(right_panel, stretch=3)
        main_layout.addLayout(content_layout)

    def trigger_cycle(self):
        # Clear graphs for new cycle
        self.time_data.clear()
        self.volt_data.clear()
        self.curr_data.clear()
        self.start_time = time.time()
        self.progress_bar.setValue(0)
        self.lbl_grade.setText("TESTING...")
        self.lbl_grade.setStyleSheet("color: #FFEA00; background: #333;")
        
        threading.Thread(target=self.master.run_automated_cycle, daemon=True).start()

    def trigger_stop(self):
        self.log_msg(">>> EMERGENCY STOP INITIATED <<<")
        self.master.send_command("STOP_CONVEYOR")
        self.master.wait_flag = False
        self.progress_bar.setValue(0)
        self.lbl_grade.setText("ABORTED")
        self.lbl_grade.setStyleSheet("color: #FF1744; background: #B71C1C;")

    def log_msg(self, msg):
        self.log_console.appendPlainText(f"{time.strftime('%H:%M:%S')} | {msg}")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())
        
        # Update progress bar heuristically based on logs
        if "Evaluating Vision" in msg: self.progress_bar.setValue(20)
        elif "Moving to Sensor" in msg: self.progress_bar.setValue(40)
        elif "Measuring" in msg: self.progress_bar.setValue(60)
        elif "Grading Decision" in msg: self.progress_bar.setValue(80)

    def update_progress(self, val):
        self.progress_bar.setValue(val)

    def update_telemetry(self, data):
        v = data.get('volt', 0)
        i = data.get('curr', 0)
        soh = data.get('soh', 0)
        
        self.lbl_volt.setText(f"{v:.2f} V")
        self.lbl_curr.setText(f"{i:.2f} A")
        self.lbl_soh.setText(f"{soh:.1f} %")
        
        # Update live graph
        t = time.time() - self.start_time
        self.time_data.append(t)
        self.volt_data.append(v)
        self.curr_data.append(i)
        
        # Keep last 50 data points to avoid crowding
        if len(self.time_data) > 50:
            self.time_data.pop(0)
            self.volt_data.pop(0)
            self.curr_data.pop(0)
            
        self.curve_v.setData(self.time_data, self.volt_data)
        self.curve_i.setData(self.time_data, self.curr_data)
        
        grade = data.get('grade', '--')
        if grade != '--':
            self.lbl_grade.setText(f"GRADE {grade}")
            if grade == 'A':
                self.lbl_grade.setStyleSheet("color: #00E676; background: #1B5E20;")
            elif grade == 'B':
                self.lbl_grade.setStyleSheet("color: #FFD600; background: #F57F17;")
            elif grade == 'R':
                self.lbl_grade.setStyleSheet("color: #FF1744; background: #B71C1C;")

    def update_camera_frame(self, frame):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        qt_img = QImage(rgb_image.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        self.cam_label.setPixmap(pixmap.scaled(self.cam_label.width(), self.cam_label.height(), Qt.KeepAspectRatio))

    def closeEvent(self, event):
        self.master.running = False
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RecellDashboard()
    window.show()
    sys.exit(app.exec_())
