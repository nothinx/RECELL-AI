import sys
import cv2
import numpy as np
import threading
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QGroupBox, QPlainTextEdit
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QImage, QPixmap

# Import core master logic
from main import RecellMaster

class UIBridge(QObject):
    """Bridge for safely passing thread data to PyQt GUI main thread."""
    frame_signal = pyqtSignal(np.ndarray)
    telemetry_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(str)

class RecellDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RECELL-AI Industrial Dashboard")
        self.setGeometry(100, 100, 1024, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")

        # Set up UI Components
        self.initUI()
        
        # Bridge for thread-safe UI updates
        self.bridge = UIBridge()
        self.bridge.frame_signal.connect(self.update_camera_frame)
        self.bridge.telemetry_signal.connect(self.update_telemetry)
        self.bridge.log_signal.connect(self.log_msg)

        # Initialize Master Controller in background
        self.init_master()

    def init_master(self):
        self.log_msg("Booting RECELL-AI Engine...")
        
        # Setup callbacks so core logic can talk to the UI
        callbacks = {
            'on_frame': self.bridge.frame_signal.emit,
            'on_telemetry': self.bridge.telemetry_signal.emit,
            'on_log': self.bridge.log_signal.emit
        }
        
        # Start RecellMaster (Use sim=True, mock_ai=True if no hardware is attached)
        self.master = RecellMaster(simulate=True, mock_ai=True, ui_callbacks=callbacks)
        
        # Start master threads
        self.master_thread = threading.Thread(target=self.master.run, daemon=True)
        self.master_thread.start()

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

        # Left: Camera Feed
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
        self.lbl_grade.setStyleSheet("color: #FFFFFF;")

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
        btn_start.clicked.connect(self.trigger_cycle)
        
        btn_stop = QPushButton("EMERGENCY STOP")
        btn_stop.setStyleSheet("background-color: #dc3545; color: white; padding: 15px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        btn_stop.clicked.connect(self.trigger_stop)

        ctrl_layout.addWidget(btn_start)
        ctrl_layout.addWidget(btn_stop)
        right_panel.addLayout(ctrl_layout)

        content_layout.addLayout(right_panel)
        layout.addLayout(content_layout)

    def trigger_cycle(self):
        # Run cycle in background so UI doesn't freeze
        threading.Thread(target=self.master.run_automated_cycle, daemon=True).start()

    def trigger_stop(self):
        self.log_msg(">>> EMERGENCY STOP INITIATED <<<")
        self.master.send_command("STOP_CONVEYOR")
        self.master.wait_flag = False

    def log_msg(self, msg):
        self.log_console.appendPlainText(f"> {msg}")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def update_telemetry(self, data):
        self.lbl_volt.setText(f"Voltage: {data.get('volt', 0):.2f} V")
        self.lbl_curr.setText(f"Current: {data.get('curr', 0):.2f} A")
        
        grade = data.get('grade', '--')
        self.lbl_grade.setText(f"Predicted Grade: {grade} (SoH: {data.get('soh',0):.1f}%)")
        if grade == 'A':
            self.lbl_grade.setStyleSheet("color: #00FF00;")
        elif grade == 'B':
            self.lbl_grade.setStyleSheet("color: #FFD700;")
        elif grade == 'R':
            self.lbl_grade.setStyleSheet("color: #FF0000;")

    def update_camera_frame(self, frame):
        # Convert BGR (OpenCV) to RGB (PyQt)
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        
        # Scale keeping aspect ratio
        scaled_pixmap = pixmap.scaled(self.cam_label.width(), self.cam_label.height(), Qt.KeepAspectRatio)
        self.cam_label.setPixmap(scaled_pixmap)

    def closeEvent(self, event):
        self.master.running = False
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RecellDashboard()
    window.show()
    sys.exit(app.exec_())
