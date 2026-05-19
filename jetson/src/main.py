import cv2
import serial
import threading
import time
import json
import argparse
import sys
import os
import xgboost as xgb
import pandas as pd
from passport_generator import BatteryPassport

# Default Configuration
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
MODEL_PATH = 'models/recell_yolo_v8n.engine'
XGB_MODEL_PATH = 'models/weights/soh_xgb_model.json'
PASSPORT_DIR = 'data/passports'

class RecellMaster:
    def __init__(self, simulate=False, mock_ai=False, ui_callbacks=None):
        self.simulate = simulate
        self.mock_ai = mock_ai
        self.running = True
        self.ser = None
        self.passport_gen = BatteryPassport(output_dir=PASSPORT_DIR)
        
        self.grade_decision = None
        self.vision_score = 1.0
        self.electrical_data = {"soh": 0, "volt": 0, "curr": 0}
        self.latest_frame = None
        
        # UI Callbacks
        self.ui_callbacks = ui_callbacks or {}
        self.wait_flag = False

        self.log_msg("=== RECELL-AI Master Controller ===")
        self.log_msg(f"Simulation Mode : {self.simulate}")
        self.log_msg(f"Mock AI Mode    : {self.mock_ai}")
        self.log_msg("===================================")

        # Initialize Vision (YOLO)
        if not self.mock_ai:
            try:
                from ultralytics import YOLO
                self.log_msg(f"[AI] Loading YOLO model: {MODEL_PATH}")
                self.model = YOLO(MODEL_PATH, task='detect')
            except Exception as e:
                self.log_msg(f"[AI] Failed to load YOLO: {e}. Falling back to MOCK_AI.")
                self.mock_ai = True

        # Initialize Electrical SOH AI (XGBoost)
        self.xgb_model = xgb.XGBRegressor()
        try:
            self.xgb_model.load_model(XGB_MODEL_PATH)
            self.log_msg(f"[AI] Loaded XGBoost SOH Model from {XGB_MODEL_PATH}")
            self.has_xgb = True
        except Exception as e:
            self.log_msg(f"[AI] Failed to load XGBoost: {e}. Will use hardcoded SOH rules.")
            self.has_xgb = False

        if not self.simulate:
            try:
                self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
                self.log_msg(f"[Comm] Connected to STM32 on {SERIAL_PORT}")
            except Exception as e:
                self.log_msg(f"[Comm] Error connecting to Serial: {e}. Falling back to SIMULATION.")
                self.simulate = True

    def log_msg(self, msg):
        print(msg)
        if 'on_log' in self.ui_callbacks:
            self.ui_callbacks['on_log'](msg)

    def vision_thread(self):
        if self.mock_ai:
            while self.running:
                time.sleep(1) 
            return

        cap = cv2.VideoCapture(0)
        while self.running:
            ret, frame = cap.read()
            if not ret: continue
            
            results = self.model(frame, verbose=False)
            
            # Draw bounding boxes for UI
            annotated_frame = results[0].plot()
            self.latest_frame = annotated_frame.copy()
            
            if 'on_frame' in self.ui_callbacks:
                self.ui_callbacks['on_frame'](annotated_frame)
                
            self.process_ai_results(results)
        cap.release()

    def process_ai_results(self, results):
        score = 1.0
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]
                if label in ['leaking', 'major_dent']: score = 0.0
                elif label == 'rust': score -= 0.3
                elif label == 'dent': score -= 0.2
        self.vision_score = max(0, score)

    def trigger_telemetry_update(self):
        if 'on_telemetry' in self.ui_callbacks:
            self.ui_callbacks['on_telemetry']({
                "volt": self.electrical_data["volt"],
                "curr": self.electrical_data["curr"],
                "soh": self.electrical_data["soh"],
                "vision_score": self.vision_score,
                "grade": self.grade_decision or "--"
            })

    def serial_listener(self):
        while self.running:
            if not self.simulate and self.ser and self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8').strip()
                try:
                    data = json.loads(line)
                    
                    if data.get("status") == "MEASUREMENT_DONE":
                        v = data.get("volt", 0)
                        i = data.get("curr", 0.001)
                        
                        self.electrical_data["volt"] = v
                        self.electrical_data["curr"] = i
                        
                        if self.has_xgb:
                            v_drop = 4.2 - v
                            internal_r = v_drop / i
                            temp_delta = 1.0 
                            features = pd.DataFrame([[v_drop, internal_r, temp_delta]], columns=['v_drop', 'internal_r', 'temp_delta'])
                            pred_soh = self.xgb_model.predict(features)[0]
                            self.electrical_data["soh"] = max(0, min(100, float(pred_soh)))
                        else:
                            self.electrical_data["soh"] = 85.0 if v > 3.6 else 40.0
                            
                        self.trigger_telemetry_update()
                        self.wait_flag = False
                        
                    elif data.get("status") in ["AT_PROX_1", "AT_PROX_2", "EJECTED_A", "DROPPED_B"]:
                        self.wait_flag = False
                        
                except:
                    pass
            time.sleep(0.01)

    def send_command(self, cmd, params=None):
        packet = {"cmd": cmd}
        if params: packet.update(params)
        payload = json.dumps(packet) + '\n'
        if self.simulate:
            self.log_msg(f"[Simulate-TX] {payload.strip()}")
            if cmd == "APPLY_SENSOR_AND_MEASURE":
                self.electrical_data["volt"] = 3.8
                self.electrical_data["curr"] = 1.2
                self.electrical_data["soh"] = 88.5
                self.trigger_telemetry_update()
            self.wait_flag = False 
        else:
            if self.ser: self.ser.write(payload.encode())

    def calculate_final_grade(self):
        soh = self.electrical_data.get("soh", 0)
        if self.vision_score < 0.4 or soh < 60: return "R"
        elif self.vision_score > 0.8 and soh > 80: return "A"
        else: return "B"

    def run_automated_cycle(self):
        self.log_msg("--- Starting Full Automated Cycle ---")
        battery_id = f"BAT_{int(time.time())}"
        img_path = f"data/{battery_id}.jpg"
        
        self.log_msg("[1] Evaluating Vision...")
        time.sleep(1) 
        if self.latest_frame is not None:
            cv2.imwrite(img_path, self.latest_frame)
        elif self.simulate: 
            with open(img_path, 'w') as f: f.write("mock")

        self.log_msg("[2] Moving to Sensor Station (PROX 1)...")
        self.wait_flag = True
        self.send_command("MOVE_TO_PROX_1")
        while self.wait_flag and self.running: time.sleep(0.1)

        self.log_msg("[3] Pushing Sensor and Measuring...")
        self.wait_flag = True
        self.send_command("APPLY_SENSOR_AND_MEASURE")
        while self.wait_flag and self.running: time.sleep(0.1)
        
        self.grade_decision = self.calculate_final_grade()
        self.trigger_telemetry_update()
        self.log_msg(f"[4] Grading Decision: {self.grade_decision} (VS: {self.vision_score:.2f}, SOH: {self.electrical_data['soh']:.1f}%)")
        
        pdf_path = self.passport_gen.generate_pdf(
            battery_id=battery_id, grade=self.grade_decision, vision_score=self.vision_score,
            volt=self.electrical_data['volt'], curr=self.electrical_data['curr'],
            soh=self.electrical_data['soh'], image_path=img_path
        )
        self.log_msg(f"[5] Battery Passport Generated: {pdf_path}")

        if self.grade_decision == "A":
            self.log_msg("[6] Routing to Grade A Bin (PROX 2)...")
            self.wait_flag = True
            self.send_command("MOVE_TO_PROX_2")
            while self.wait_flag and self.running: time.sleep(0.1)
            
            self.log_msg("[7] Ejecting Grade A...")
            self.wait_flag = True
            self.send_command("EJECT_A")
            while self.wait_flag and self.running: time.sleep(0.1)
        else:
            self.log_msg("[6] Routing to Grade B / Reject Bin (END OF CONVEYOR)...")
            self.wait_flag = True
            self.send_command("MOVE_TO_END")
            while self.wait_flag and self.running: time.sleep(0.1)
            
        self.log_msg("--- Cycle Complete ---")

    def run(self):
        threading.Thread(target=self.vision_thread, daemon=True).start()
        threading.Thread(target=self.serial_listener, daemon=True).start()
        # If UI handles lifecycle, don't run CLI
        if not self.ui_callbacks:
            self.interactive_cli()
            self.log_msg("[System] Shutting down...")

    def interactive_cli(self):
        print("\n--- Hardware Test Menu ---")
        print("1: Full Automated Cycle")
        print("q: Quit")
        
        if not os.path.exists("data"): os.makedirs("data")

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
