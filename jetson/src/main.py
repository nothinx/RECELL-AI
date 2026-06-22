import cv2
import serial
import threading
import time
import json
import argparse
import sys
import os
from pathlib import Path
try:
    import xgboost as xgb
    _HAS_XGBOOST = True
except ImportError:
    xgb = None
    _HAS_XGBOOST = False
import pandas as pd
from collections import defaultdict

from passport_generator import BatteryPassport
from data_logger import DataLogger

# Anchor every path to the jetson/ directory so we can run from anywhere.
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
PASSPORT_DIR = DATA_DIR / "passports"
LOG_DIR = DATA_DIR / "logs"

# Default Configuration
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
YOLO_ENGINE_PATH = MODELS_DIR / "weights" / "best.engine"   # preferred on Jetson
YOLO_PT_PATH = MODELS_DIR / "weights" / "best.pt"           # fallback (dev / non-Jetson)
XGB_MODEL_PATH = MODELS_DIR / "weights" / "soh_xgb_model.json"
CALIB_PATH = BASE_DIR / "calibration.json"

# Hardware motion defaults. Conveyor lowered after the trial showed it
# over-shooting the IR sensor even at PWM 30. Tune live via the F12 / on-screen
# calibration panel; values persist to calibration.json and are pushed to the
# STM32 on every connect.
DEFAULT_CALIBRATION = {"conveyor_speed": 25, "step_pulse_us": 50}

# Map YOLO class label -> (delta to vision_score, is_critical)
# Classes from best.pt: KARAT (rust), SEHAT (healthy), SOBEK (torn wrapper)
CLASS_RULES = {
    "KARAT":  {"delta": -0.4, "critical": False},
    "SOBEK":  {"delta": 0.0,  "critical": True},   # any SOBEK -> reject
    "SEHAT":  {"delta": 0.0,  "critical": False},  # neutral positive
}

# A defect class must be detected in at least this many *frames* during a
# cycle before it counts toward the grade. Filters transient false positives.
DEFECT_PERSIST_FRAMES = 3


class RecellMaster:
    def __init__(self, simulate=False, mock_ai=False, ui_callbacks=None):
        self.simulate = simulate
        self.mock_ai = mock_ai
        self.running = True
        self.ser = None
        self.passport_gen = BatteryPassport(output_dir=str(PASSPORT_DIR))
        self.logger = DataLogger(output_dir=str(LOG_DIR))

        # Hardware/AI status (consumed by UI status indicators)
        self.status = {
            "camera": "offline",   # offline | online | mock
            "serial": "offline",   # offline | online | sim
            "yolo":   "offline",   # offline | online | mock
            "xgb":    "offline",   # offline | online | rule
        }

        self.grade_decision = None
        self.vision_score = 1.0
        self.electrical_data = {"soh": 0, "volt": 0, "curr": 0}
        self.latest_frame = None
        self.current_battery_id = None
        # Count how many frames in the current cycle saw each label, so a
        # single false-positive frame doesn't permanently mark a defect.
        self.defect_frame_counts = defaultdict(int)
        self.measurement_detail = {}

        # UI Callbacks
        self.ui_callbacks = ui_callbacks or {}
        self.wait_flag = False
        self.abort_cycle = False  # set by Emergency Stop, breaks _simulate_measurement

        self._serial_lock = threading.Lock()        # #5: guard serial r/w across threads
        self._camera_restart_requested = False      # #8: set by restart_camera()
        self.calibration = self._load_calibration()

        self.log_msg("=== RECELL-AI Master Controller ===")
        self.log_msg(f"Simulation Mode : {self.simulate}")
        self.log_msg(f"Mock AI Mode    : {self.mock_ai}")
        self.log_msg(f"Base directory  : {BASE_DIR}")
        self.log_msg("===================================")

        # Initialize Vision (YOLO)
        self.model = None
        if not self.mock_ai:
            # Matikan telemetry/sync SEBELUM init — mencegah HTTP call di Jetson air-gapped.
            # setup.sh sudah mempersistnya ke ~/.config/Ultralytics/settings.yaml, tapi
            # ini adalah fallback agar efektif bahkan saat dijalankan di laptop dev.
            try:
                from ultralytics import settings as _uly
                _uly.update({"sync": False})
            except Exception:
                pass
            try:
                from ultralytics import YOLO
                if YOLO_ENGINE_PATH.exists():
                    self.log_msg(f"[AI] Loading TensorRT engine: {YOLO_ENGINE_PATH}")
                    self.model = YOLO(str(YOLO_ENGINE_PATH), task="detect")
                elif YOLO_PT_PATH.exists():
                    self.log_msg(f"[AI] Loading PyTorch model: {YOLO_PT_PATH}")
                    self.model = YOLO(str(YOLO_PT_PATH))
                else:
                    raise FileNotFoundError(
                        f"No model found at {YOLO_ENGINE_PATH} or {YOLO_PT_PATH}"
                    )
                self.log_msg(f"[AI] YOLO classes: {self.model.names}")
                self.status["yolo"] = "online"
            except Exception as e:
                self.log_msg(f"[AI] Failed to load YOLO ({e}). Falling back to MOCK_AI.")
                self.mock_ai = True
                self.status["yolo"] = "mock"
        else:
            self.status["yolo"] = "mock"

        # Initialize Electrical SOH AI (XGBoost). The package itself is optional:
        # on a dev box without xgboost installed the app still runs end-to-end
        # with rule-based SOH instead of crashing at import.
        self.xgb_model = None
        if not _HAS_XGBOOST:
            self.log_msg("[AI] xgboost not installed — using hardcoded SOH rules.")
            self.has_xgb = False
            self.status["xgb"] = "rule"
        else:
            self.xgb_model = xgb.XGBRegressor()
            try:
                self.xgb_model.load_model(str(XGB_MODEL_PATH))
                self.log_msg(f"[AI] Loaded XGBoost SOH Model from {XGB_MODEL_PATH}")
                self.has_xgb = True
                self.status["xgb"] = "online"
            except Exception as e:
                self.log_msg(f"[AI] Failed to load XGBoost: {e}. Will use hardcoded SOH rules.")
                self.has_xgb = False
                self.status["xgb"] = "rule"

        if not self.simulate:
            try:
                self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
                self.log_msg(f"[Comm] Connected to STM32 on {SERIAL_PORT}")
                self.status["serial"] = "online"
                time.sleep(2)  # let the board finish booting before config
                self.send_command("SET_CONFIG", self.calibration)
                self.log_msg(f"[Comm] Pushed calibration: {self.calibration}")
            except Exception as e:
                self.log_msg(f"[Comm] Error connecting to Serial: {e}. Falling back to SIMULATION.")
                self.simulate = True
                self.status["serial"] = "sim"
        else:
            self.status["serial"] = "sim"

        self._notify_status()

    def _notify_status(self):
        if "on_status" in self.ui_callbacks:
            self.ui_callbacks["on_status"](dict(self.status))

    @staticmethod
    def list_serial_ports():
        """Return list of (port, description) for all detected serial devices."""
        from serial.tools import list_ports
        return [(p.device, p.description) for p in list_ports.comports()]

    def reconnect_serial(self, port, baud=115200):
        """Close existing serial connection and open a new one on *port*."""
        with self._serial_lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            try:
                self.ser = serial.Serial(port, baud, timeout=0.1)
                self.simulate = False
                self.status["serial"] = "online"
                self.log_msg(f"[Comm] Reconnected to STM32 on {port} @ {baud} baud")
            except Exception as e:
                self.simulate = True
                self.status["serial"] = "offline"
                self.log_msg(f"[Comm] Failed to connect to {port}: {e}")
        # Push calibration outside the lock (send_command re-acquires it).
        if self.status["serial"] == "online":
            self.send_command("SET_CONFIG", self.calibration)
        self._notify_status()
        return self.status["serial"] == "online"

    def disconnect_serial(self):
        """Close serial port and switch to simulation mode."""
        with self._serial_lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
        self.simulate = True
        self.status["serial"] = "sim"
        self.log_msg("[Comm] Serial disconnected — simulation mode active")
        self._notify_status()

    def restart_camera(self):
        """Minta vision_thread untuk menutup dan membuka ulang kamera."""
        self._camera_restart_requested = True
        self.status["camera"] = "offline"
        self._notify_status()
        self.log_msg("[Camera] Restart diminta…")

    def override_grade(self, new_grade):
        """Override keputusan AI dengan grade manual dari operator."""
        old = self.grade_decision
        self.grade_decision = new_grade
        self.log_msg(f"[Override] Grade diubah: {old} → {new_grade} (manual operator)")
        self.trigger_telemetry_update()

    def log_msg(self, msg):
        print(msg)
        if 'on_log' in self.ui_callbacks:
            self.ui_callbacks['on_log'](msg)

    def vision_thread(self):
        """Loop utama kamera — restart otomatis jika restart_camera() dipanggil."""
        while self.running:
            self._camera_restart_requested = False
            self._run_camera_session()
            # Keluar loop hanya jika running=False (shutdown) atau restart diminta
            if not self._camera_restart_requested:
                break

    def _run_camera_session(self):
        """Satu sesi kamera: buka, inferensi, tutup. Bisa diulang oleh vision_thread."""
        if self.mock_ai:
            while self.running and not self._camera_restart_requested:
                time.sleep(0.5)
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.log_msg("[Camera] Tidak ada kamera (VideoCapture(0) gagal). Mode MOCK.")
            self.status["camera"] = "mock"
            self._notify_status()
            cap.release()
            while self.running and not self._camera_restart_requested:
                time.sleep(0.5)
            return

        self.status["camera"] = "online"
        self._notify_status()
        self.log_msg("[Camera] Kamera aktif, memulai inferensi YOLO.")

        FRAME_PERIOD = 0.04  # ~25 FPS cap
        try:
            while self.running and not self._camera_restart_requested:
                t0 = time.time()
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                try:
                    results = self.model(frame, verbose=False)
                    annotated_frame = results[0].plot()
                    self.latest_frame = annotated_frame.copy()
                    if 'on_frame' in self.ui_callbacks:
                        self.ui_callbacks['on_frame'](annotated_frame)
                    self.process_ai_results(results)
                except Exception as e:
                    self.log_msg(f"[Vision] inference error: {e}")
                    time.sleep(0.1)
                elapsed = time.time() - t0
                if elapsed < FRAME_PERIOD:
                    time.sleep(FRAME_PERIOD - elapsed)
        finally:
            cap.release()
            if self._camera_restart_requested:
                self.log_msg("[Camera] Sesi ditutup, membuka ulang…")
                time.sleep(1)

    def process_ai_results(self, results):
        # Count each label at most once per frame: many boxes of the same
        # class shouldn't multiply the penalty.
        labels_this_frame = set()
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                labels_this_frame.add(self.model.names[cls_id])
        for label in labels_this_frame:
            self.defect_frame_counts[label] += 1

        # Live vision_score reflects only labels that have persisted across
        # enough frames. SEHAT is informational, KARAT/SOBEK shape the score.
        score = 1.0
        critical_hit = False
        for label, count in self.defect_frame_counts.items():
            if count < DEFECT_PERSIST_FRAMES:
                continue
            rule = CLASS_RULES.get(label)
            if not rule:
                continue
            if rule["critical"]:
                critical_hit = True
            score += rule["delta"]
        if critical_hit:
            score = 0.0
        self.vision_score = max(0.0, min(1.0, score))

    def get_confirmed_defects(self):
        """Defect labels that passed the per-frame persistence threshold."""
        return sorted(
            lbl for lbl, c in self.defect_frame_counts.items()
            if c >= DEFECT_PERSIST_FRAMES
        )

    def trigger_telemetry_update(self):
        if 'on_telemetry' in self.ui_callbacks:
            self.ui_callbacks['on_telemetry']({
                "volt": self.electrical_data["volt"],
                "curr": self.electrical_data["curr"],
                "soh": self.electrical_data["soh"],
                "vision_score": self.vision_score,
                "grade": self.grade_decision or "--",
                "defects": self.get_confirmed_defects(),
            })

    def _emit_discharge_sample(self, t_ms, voltage, current, temp):
        if 'on_discharge_sample' in self.ui_callbacks:
            self.ui_callbacks['on_discharge_sample']({
                "t_ms": t_ms, "voltage": voltage, "current": current, "temp": temp,
            })

    def serial_listener(self):
        while self.running:
            with self._serial_lock:
                ready = (not self.simulate and self.ser and self.ser.in_waiting > 0)
                line = self.ser.readline().decode('utf-8', errors='ignore').strip() if ready else None
            if line:
                try:
                    data = json.loads(line)
                    if data.get("status") == "MEASUREMENT_DONE":
                        v = data.get("volt", 0)
                        i = data.get("curr", 0.001)
                        t_delta = float(data.get("temp_delta", 1.0))
                        v_resting = float(data.get("v_resting", 4.2))
                        temp_pre = float(data.get("temp_pre", 25.0))
                        temp_post = float(data.get("temp_post", temp_pre + t_delta))
                        self.electrical_data["volt"] = v
                        self.electrical_data["curr"] = i
                        v_drop = v_resting - v
                        safe_i = i if i > 0 else 0.001
                        internal_r = v_drop / safe_i
                        if self.has_xgb:
                            features = pd.DataFrame(
                                [[v_drop, internal_r, t_delta]],
                                columns=['v_drop', 'internal_r', 'temp_delta'])
                            pred_soh = self.xgb_model.predict(features)[0]
                            self.electrical_data["soh"] = max(0, min(100, float(pred_soh)))
                        else:
                            self.electrical_data["soh"] = 85.0 if v > 3.6 else 40.0
                        self.measurement_detail = {
                            "v_resting": v_resting,
                            "v_loaded": v,
                            "v_drop": v_drop,
                            "current_load": i,
                            "internal_r": internal_r,
                            "temp_pre": temp_pre,
                            "temp_post": temp_post,
                            "temp_delta": t_delta,
                        }
                        self.trigger_telemetry_update()
                        self.wait_flag = False
                    elif data.get("status") == "DISCHARGE_SAMPLE":
                        t_ms = data.get("t_ms", 0)
                        v = data.get("volt", 0)
                        i = data.get("curr", 0)
                        t = data.get("temp", 0)
                        if self.current_battery_id:
                            self.logger.log_discharge_sample(
                                self.current_battery_id, t_ms, v, i, t)
                        self._emit_discharge_sample(t_ms, v, i, t)
                    elif data.get("status") in ["AT_PROX_1", "AT_PROX_2", "EJECTED_A", "DROPPED_B"]:
                        self.wait_flag = False
                    elif data.get("status") == "EMERGENCY_STOP":
                        self.log_msg("[STM32] HARDWARE EMERGENCY STOP — aborting cycle.")
                        self.abort_cycle = True
                        self.wait_flag = False
                    elif data.get("status") == "STEP_TIMEOUT":
                        self.log_msg("[STM32] STEP TIMEOUT — firmware aborted a step. Aborting cycle.")
                        self.abort_cycle = True
                        self.wait_flag = False
                    elif data.get("status") == "CONFIG_OK":
                        self.log_msg(f"[STM32] Calibration applied: speed={data.get('volt')} pulse={data.get('curr')}")
                    elif data.get("status") == "JOGGING":
                        self.log_msg("[STM32] Conveyor jogging (manual stop / 10 s auto-stop).")
                    elif data.get("status") == "BOOT_OK":
                        # Board (re)booted — re-push calibration so it survives a reset.
                        self.send_command("SET_CONFIG", self.calibration)
                        self.log_msg(f"[STM32] Boot detected — re-pushed calibration: {self.calibration}")
                except Exception:
                    pass
            time.sleep(0.01)

    def send_command(self, cmd, params=None):
        packet = {"cmd": cmd}
        if params:
            packet.update(params)
        payload = json.dumps(packet) + '\n'
        if self.simulate:
            self.log_msg(f"[Simulate-TX] {payload.strip()}")
            if cmd == "APPLY_SENSOR_AND_MEASURE":
                self._simulate_measurement()
            self.wait_flag = False
        else:
            with self._serial_lock:
                if self.ser:
                    self.ser.write(payload.encode())

    # ----- CALIBRATION ------------------------------------------------------
    def _load_calibration(self):
        cfg = dict(DEFAULT_CALIBRATION)
        try:
            with open(CALIB_PATH) as f:
                cfg.update({k: int(v) for k, v in json.load(f).items()
                            if k in DEFAULT_CALIBRATION})
        except Exception:
            pass  # missing/invalid file -> defaults
        return cfg

    def set_calibration(self, conveyor_speed, step_pulse_us, save=True):
        """Update motion config, push it to the STM32, and optionally persist."""
        self.calibration = {
            "conveyor_speed": max(0, min(255, int(conveyor_speed))),
            "step_pulse_us": max(20, min(5000, int(step_pulse_us))),
        }
        self.send_command("SET_CONFIG", self.calibration)
        if save:
            try:
                with open(CALIB_PATH, "w") as f:
                    json.dump(self.calibration, f, indent=2)
                self.log_msg(f"[Calib] Saved {self.calibration} -> {CALIB_PATH}")
            except Exception as e:
                self.log_msg(f"[Calib] Could not save calibration: {e}")
        return self.calibration

    def jog_forward(self):
        """Run the conveyor forward continuously (setup speed test)."""
        self.send_command("JOG_FWD")

    def stop_conveyor(self):
        self.send_command("STOP_CONVEYOR")

    def _simulate_measurement(self):
        """Produce a realistic measurement and a short discharge curve in --sim mode.

        Samples are emitted to the UI at the natural 20 ms cadence so the live
        plot reflects what real hardware would look like.
        """
        import random
        soh_true = random.choice([
            random.uniform(82, 98),
            random.uniform(60, 80),
            random.uniform(30, 55),
        ])
        v_resting = 4.2 - (100 - soh_true) * 0.004 + random.uniform(-0.02, 0.02)
        internal_r = 0.05 + (100 - soh_true) * 0.004 + random.uniform(-0.01, 0.01)
        current_load = 1.0
        v_loaded = v_resting - internal_r * current_load
        v_drop = v_resting - v_loaded
        temp_pre = 25.0 + random.uniform(-1, 1)
        temp_delta = 0.5 + (100 - soh_true) * 0.05 + random.uniform(-0.2, 0.2)
        temp_post = temp_pre + temp_delta

        # Stream the discharge curve in real time (20 ms cadence over ~2 s).
        samples = []
        for t_ms in range(0, 2001, 20):
            v_t = v_resting - v_drop * (1 - 2.718 ** (-t_ms / 200.0))
            temp_t = temp_pre + temp_delta * (t_ms / 2000.0)
            v_t = round(v_t, 4)
            temp_t = round(temp_t, 2)
            samples.append((t_ms, v_t, current_load, temp_t))
            self._emit_discharge_sample(t_ms, v_t, current_load, temp_t)
            if not self.running or self.abort_cycle:
                break
            time.sleep(0.02)

        if self.current_battery_id:
            self.logger.log_discharge_batch(self.current_battery_id, samples)

        self.electrical_data["volt"] = v_loaded
        self.electrical_data["curr"] = current_load
        self.measurement_detail = {
            "v_resting": v_resting,
            "v_loaded": v_loaded,
            "v_drop": v_drop,
            "current_load": current_load,
            "internal_r": internal_r,
            "temp_pre": temp_pre,
            "temp_post": temp_post,
            "temp_delta": temp_delta,
        }

        if self.has_xgb:
            features = pd.DataFrame(
                [[v_drop, internal_r, temp_delta]],
                columns=['v_drop', 'internal_r', 'temp_delta'])
            pred_soh = float(self.xgb_model.predict(features)[0])
            self.electrical_data["soh"] = max(0, min(100, pred_soh))
        else:
            self.electrical_data["soh"] = soh_true + random.uniform(-3, 3)

        # When YOLO isn't running (mock or no camera), synthesize a vision score
        # that's correlated with SOH so the demo cycle produces varied grades.
        if self.mock_ai or self.status["camera"] != "online":
            self.vision_score = max(0.0, min(1.0, 0.5 + (self.electrical_data["soh"] - 60) / 80))

        self.trigger_telemetry_update()

    def calculate_final_grade(self):
        soh = self.electrical_data.get("soh", 0)
        if self.vision_score < 0.4 or soh < 60:
            return "R"
        elif self.vision_score > 0.8 and soh > 80:
            return "A"
        else:
            return "B"

    def run_automated_cycle(self, ground_truth=None):
        self.log_msg("--- Starting Full Automated Cycle ---")
        cycle_start = time.time()
        battery_id = time.strftime("RC-%Y%m%d-%H%M%S")
        self.current_battery_id = battery_id
        self.defect_frame_counts = defaultdict(int)
        self.measurement_detail = {}
        self.abort_cycle = False  # clear any previous abort
        # Reset grade so UI shows TESTING state cleanly
        self.grade_decision = None

        # Clear any latched hardware E-stop on the STM32 so a cycle started after
        # an emergency doesn't hang on a silently-dropped command. Fire-and-forget:
        # firmware replies RESET_OK (not awaited). If the physical button is still
        # held, firmware re-enters EMERGENCY immediately.
        self.send_command("RESET")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        img_path = str(DATA_DIR / f"{battery_id}.jpg")

        self.log_msg("[1] Evaluating Vision...")
        time.sleep(1)
        if self.latest_frame is not None:
            cv2.imwrite(img_path, self.latest_frame)
        else:
            # No camera frame available: skip writing a placeholder. The PDF
            # generator falls back to "[No Photo Available]" when the path
            # doesn't exist.
            img_path = ""

        self.log_msg("[2] Moving to Sensor Station (PROX 1)...")
        self.wait_flag = True
        self.send_command("MOVE_TO_PROX_1")
        if not self._wait_for_step():
            return

        self.log_msg("[3] Pushing Sensor and Measuring...")
        self.wait_flag = True
        self.send_command("APPLY_SENSOR_AND_MEASURE")
        if not self._wait_for_step():
            return

        self.grade_decision = self.calculate_final_grade()
        self.trigger_telemetry_update()
        self.log_msg(
            f"[4] Grading Decision: {self.grade_decision} "
            f"(VS: {self.vision_score:.2f}, SOH: {self.electrical_data['soh']:.1f}%)")

        pdf_path = self.passport_gen.generate_pdf(
            battery_id=battery_id, grade=self.grade_decision,
            vision_score=self.vision_score,
            volt=self.electrical_data['volt'], curr=self.electrical_data['curr'],
            soh=self.electrical_data['soh'], image_path=img_path,
            measurement=self.measurement_detail,
            defects=self.get_confirmed_defects(),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self.log_msg(f"[5] Battery Passport Generated: {pdf_path}")

        cycle_time = round(time.time() - cycle_start, 2)
        m = self.measurement_detail
        self.logger.log_grading(
            battery_id=battery_id,
            cycle_time_s=cycle_time,
            v_resting=round(m.get("v_resting", 0), 4),
            v_loaded=round(m.get("v_loaded", self.electrical_data["volt"]), 4),
            v_drop=round(m.get("v_drop", 0), 4),
            current_load=round(m.get("current_load", self.electrical_data["curr"]), 4),
            internal_r=round(m.get("internal_r", 0), 4),
            temp_pre=round(m.get("temp_pre", 0), 2),
            temp_post=round(m.get("temp_post", 0), 2),
            temp_delta=round(m.get("temp_delta", 0), 2),
            soh_predicted=round(self.electrical_data["soh"], 2),
            vision_score=round(self.vision_score, 3),
            defects_detected=";".join(self.get_confirmed_defects()) or "none",
            grade_predicted=self.grade_decision,
            grade_ground_truth=ground_truth or "",
            passport_pdf=pdf_path,
        )
        self.log_msg(f"[Log] Grading row appended to {self.logger.grading_path}")

        if self.grade_decision == "A":
            self.log_msg("[6] Routing to Grade A Bin (PROX 2)...")
            self.wait_flag = True
            self.send_command("MOVE_TO_PROX_2")
            if not self._wait_for_step():
                return

            self.log_msg("[7] Ejecting Grade A...")
            self.wait_flag = True
            self.send_command("EJECT_A")
            if not self._wait_for_step():
                return
        else:
            self.log_msg("[6] Routing to Grade B / Reject Bin (END OF CONVEYOR)...")
            self.wait_flag = True
            self.send_command("MOVE_TO_END")
            if not self._wait_for_step():
                return

        self.log_msg("--- Cycle Complete ---")
        if pdf_path and 'on_passport' in self.ui_callbacks:
            self.ui_callbacks['on_passport'](pdf_path, self.grade_decision)

    def _aborted(self):
        if self.abort_cycle:
            self.log_msg("[ABORT] Cycle aborted by Emergency Stop.")
            return True
        return False

    def _wait_for_step(self, timeout=45.0):
        """Block until the firmware signals the current step is done (wait_flag
        cleared), the cycle is aborted, or `timeout` seconds elapse. Returns True
        if the step completed normally; False if it was aborted or timed out (the
        caller should stop the cycle).

        Firmware enforces its own per-step timeouts and emits STEP_TIMEOUT; this
        is a Jetson-side backstop in case that status is ever lost, so a cycle can
        never hang forever on a step that will not complete."""
        start = time.time()
        while self.wait_flag and self.running and not self.abort_cycle:
            if time.time() - start > timeout:
                self.log_msg(f"[TIMEOUT] Step exceeded {timeout:.0f}s with no response — aborting cycle.")
                self.abort_cycle = True
                self.wait_flag = False
                self.send_command("STOP_CONVEYOR")
                return False
            time.sleep(0.1)
        return not self._aborted()

    def run(self):
        threading.Thread(target=self.vision_thread, daemon=True).start()
        threading.Thread(target=self.serial_listener, daemon=True).start()
        if not self.ui_callbacks:
            self.interactive_cli()
            self.log_msg("[System] Shutting down...")

    def interactive_cli(self):
        print("\n--- Hardware Test Menu ---")
        print("1: Full Automated Cycle")
        print("q: Quit")

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        while self.running:
            try:
                choice = input("CMD> ").strip()
                if choice == '1':
                    threading.Thread(target=self.run_automated_cycle).start()
                elif choice.lower() == 'q':
                    self.running = False
            except EOFError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RECELL-AI Controller")
    parser.add_argument('--sim', action='store_true', help='Run without STM32 connected')
    parser.add_argument('--mock-ai', action='store_true', help='Run without YOLO/Camera')
    args = parser.parse_args()

    app = RecellMaster(simulate=args.sim, mock_ai=args.mock_ai)
    app.run()
