import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QGroupBox, QPlainTextEdit
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QPixmap
import json

# Import master logic (Assuming main.py is refactored to allow UI binding, but we mock it here for skeleton)
# from main import RecellMaster

class RecellDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RECELL-AI Industrial Dashboard")
        self.setGeometry(100, 100, 1024, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")

        self.initUI()
        
        # Mocking incoming data timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_telemetry_mock)
        self.timer.start(1000)

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- HEADER ---
        header_label = QLabel("RECELL-AI | Battery Grading System")
        header_label.setFont(QFont("Arial", 24, QFont.Bold))
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # --- MIDDLE CONTENT ---
        content_layout = QHBoxLayout()

        # Left: Camera Feed (Mock)
        cam_group = QGroupBox("Live Vision (YOLOv8n)")
        cam_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #333; padding: 10px; margin-top: 15px;} QGroupBox::title { subcontrol-origin: margin; top: -10px; left: 10px; }")
        cam_layout = QVBoxLayout(cam_group)
        self.cam_label = QLabel("CAMERA FEED OFFLINE")
        self.cam_label.setAlignment(Qt.AlignCenter)
        self.cam_label.setStyleSheet("background-color: #000; border: 1px solid #555;")
        self.cam_label.setMinimumSize(640, 480)
        cam_layout.addWidget(self.cam_label)
        content_layout.addWidget(cam_group)

        # Right: Telemetry & Controls
        right_panel = QVBoxLayout()

        # Telemetry Stats
        stat_group = QGroupBox("Real-Time Telemetry")
        stat_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #333; padding: 10px; margin-top: 15px;} QGroupBox::title { subcontrol-origin: margin; top: -10px; left: 10px; }")
        stat_layout = QVBoxLayout(stat_group)
        
        self.lbl_volt = QLabel("Voltage: -- V")
        self.lbl_volt.setFont(QFont("Arial", 16))
        self.lbl_curr = QLabel("Current: -- A")
        self.lbl_curr.setFont(QFont("Arial", 16))
        self.lbl_grade = QLabel("Predicted Grade: --")
        self.lbl_grade.setFont(QFont("Arial", 20, QFont.Bold))
        self.lbl_grade.setStyleSheet("color: #00FF00;")

        stat_layout.addWidget(self.lbl_volt)
        stat_layout.addWidget(self.lbl_curr)
        stat_layout.addWidget(self.lbl_grade)
        right_panel.addWidget(stat_group)

        # Serial Log Console
        log_group = QGroupBox("System Logs")
        log_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #333; padding: 10px; margin-top: 15px;} QGroupBox::title { subcontrol-origin: margin; top: -10px; left: 10px; }")
        log_layout = QVBoxLayout(log_group)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #111; font-family: monospace; font-size: 12px;")
        log_layout.addWidget(self.log_console)
        right_panel.addWidget(log_group)

        # Controls
        ctrl_layout = QHBoxLayout()
        btn_start = QPushButton("START CYCLE")
        btn_start.setStyleSheet("background-color: #28a745; color: white; padding: 15px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        btn_start.clicked.connect(lambda: self.log_msg("Command: START CYCLE"))
        
        btn_stop = QPushButton("EMERGENCY STOP")
        btn_stop.setStyleSheet("background-color: #dc3545; color: white; padding: 15px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        btn_stop.clicked.connect(lambda: self.log_msg("Command: EMERGENCY STOP"))

        ctrl_layout.addWidget(btn_start)
        ctrl_layout.addWidget(btn_stop)
        right_panel.addLayout(ctrl_layout)

        content_layout.addLayout(right_panel)
        layout.addLayout(content_layout)

    def log_msg(self, msg):
        self.log_console.appendPlainText(f"> {msg}")

    def update_telemetry_mock(self):
        # Mocking changing data
        import random
        v = round(random.uniform(3.6, 4.1), 2)
        i = round(random.uniform(0.9, 1.2), 2)
        self.lbl_volt.setText(f"Voltage: {v} V")
        self.lbl_curr.setText(f"Current: {i} A")
        
        grades = ['A', 'B', 'R (Reject)']
        colors = ['#00FF00', '#FFD700', '#FF0000']
        idx = random.randint(0, 2)
        self.lbl_grade.setText(f"Predicted Grade: {grades[idx]}")
        self.lbl_grade.setStyleSheet(f"color: {colors[idx]};")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RecellDashboard()
    window.show()
    # To run fullscreen on Jetson Kiosk: window.showFullScreen()
    sys.exit(app.exec_())
