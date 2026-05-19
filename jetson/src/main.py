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
    def __init__(self, simulate=False, mock_ai=False):
        self.simulate = simulate
        self.mock_ai = mock_ai
        self.running = True
        self.ser = None
        self.passport_gen = BatteryPassport(output_dir=PASSPORT_DIR)
        
        self.grade_decision = None
        self.vision_score = 1.0
        self.electrical_data = {"soh": 0, "volt": 0, "curr": 0}
        self.latest_frame = None

        print("=== RECELL-AI Master Controller ===")
        print(f"Simulation Mode : {self.simulate}")
        print(f"Mock AI Mode    : {self.mock_ai}")
        print("===================================")

        # Initialize Vision (YOLO)
        if not self.mock_ai:
            try:
                from ultralytics import YOLO
                print(f"[AI] Loading YOLO model: {MODEL_PATH}")
                self.model = YOLO(MODEL_PATH, task='detect')
            except Exception as e:
                print(f"[AI] Failed to load YOLO: {e}. Falling back to MOCK_AI.")
                self.mock_ai = True

        # Initialize Electrical SOH AI (XGBoost)
        self.xgb_model = xgb.XGBRegressor()
        try:
            self.xgb_model.load_model(XGB_MODEL_PATH)
            print(f"[AI] Loaded XGBoost SOH Model from {XGB_MODEL_PATH}")
            self.has_xgb = True
        except Exception as e:
            print(f"[AI] Failed to load XGBoost: {e}. Will use hardcoded SOH rules.")
            self.has_xgb = False

        if not self.simulate:
            try:
                self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
                print(f"[Comm] Connected to STM32 on {SERIAL_PORT}")
            except Exception as e:
                print(f"[Comm] Error connecting to Serial: {e}. Falling back to SIMULATION.")
                self.simulate = True

    def vision_thread(self):
        if self.mock_ai:
            while self.running:
                time.sleep(1) 
            return

        cap = cv2.VideoCapture(0)
        while self.running:
            ret, frame = cap.read()
            if not ret: continue
            
            self.latest_frame = frame.copy()
            results = self.model(frame, verbose=False)
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

    def serial_listener(self):
        while self.running:
            if not self.simulate and self.ser and self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8').strip()
                try:
                    data = json.loads(line)
                    
                    if data.get("status") == "MEASUREMENT_DONE":
                        v = data.get("volt", 0)
                        i = data.get("curr", 0.001) # Avoid div zero
                        
                        self.electrical_data["volt"] = v
                        self.electrical_data["curr"] = i
                        
                        # Calculate SOH using XGBoost if available, else fallback rule
                        if self.has_xgb:
                            # Features must match training script
                            v_drop = 4.2 - v # Assuming 4.2V is full
                            internal_r = v_drop / i
                            temp_delta = 1.0 # Mock temperature sensor reading
                            
                            features = pd.DataFrame([[v_drop, internal_r, temp_delta]], 
                                                  columns=['v_drop', 'internal_r', 'temp_delta'])
                            pred_soh = self.xgb_model.predict(features)[0]
                            self.electrical_data["soh"] = max(0, min(100, float(pred_soh)))
                        else:
                            self.electrical_data["soh"] = 85.0 if v > 3.6 else 40.0
                            
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
            print(f"\n[Simulate-TX] {payload.strip()}")
            # If measuring in sim, auto-inject mock result
            if cmd == "APPLY_SENSOR_AND_MEASURE":
                self.electrical_data["volt"] = 3.8
                self.electrical_data["curr"] = 1.2
                if self.has_xgb:
                    features = pd.DataFrame([[0.4, 0.33, 1.0]], columns=['v_drop', 'internal_r', 'temp_delta'])
                    self.electrical_data["soh"] = float(self.xgb_model.predict(features)[0])
                else:
                    self.electrical_data["soh"] = 85.0
            self.wait_flag = False 
        else:
            if self.ser: self.ser.write(payload.encode())

    def calculate_final_grade(self):
        soh = self.electrical_data.get("soh", 0)
        if self.vision_score < 0.4 or soh < 60: return "R"
        elif self.vision_score > 0.8 and soh > 80: return "A"
        else: return "B"

    def run_automated_cycle(self):
        print("\n--- Starting Full Automated Cycle ---")
        battery_id = f"BAT_{int(time.time())}"
        img_path = f"data/{battery_id}.jpg"
        
        print("[1] Evaluating Vision...")
        time.sleep(1) 
        if self.latest_frame is not None:
            cv2.imwrite(img_path, self.latest_frame)
        elif self.simulate: 
            with open(img_path, 'w') as f: f.write("mock")

        print("[2] Moving to Sensor Station (PROX 1)...")
        self.wait_flag = True
        self.send_command("MOVE_TO_PROX_1")
        while self.wait_flag: time.sleep(0.1)

        print("[3] Pushing Sensor and Measuring...")
        self.wait_flag = True
        self.send_command("APPLY_SENSOR_AND_MEASURE")
        while self.wait_flag: time.sleep(0.1)
        
        grade = self.calculate_final_grade()
        print(f"[4] Grading Decision: {grade} (VS: {self.vision_score:.2f}, SOH: {self.electrical_data['soh']:.1f}%)")
        
        pdf_path = self.passport_gen.generate_pdf(
            battery_id=battery_id, grade=grade, vision_score=self.vision_score,
            volt=self.electrical_data['volt'], curr=self.electrical_data['curr'],
            soh=self.electrical_data['soh'], image_path=img_path
        )
        print(f"[5] Battery Passport Generated: {pdf_path}")

        if grade == "A":
            print("[6] Routing to Grade A Bin (PROX 2)...")
            self.wait_flag = True
            self.send_command("MOVE_TO_PROX_2")
            while self.wait_flag: time.sleep(0.1)
            
            print("[7] Ejecting Grade A...")
            self.wait_flag = True
            self.send_command("EJECT_A")
            while self.wait_flag: time.sleep(0.1)
        else:
            print("[6] Routing to Grade B / Reject Bin (END OF CONVEYOR)...")
            self.wait_flag = True
            self.send_command("MOVE_TO_END")
            while self.wait_flag: time.sleep(0.1)
            
        print("--- Cycle Complete ---\nCMD> ", end="")

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

    def run(self):
        threading.Thread(target=self.vision_thread, daemon=True).start()
        threading.Thread(target=self.serial_listener, daemon=True).start()
        self.interactive_cli()
        print("[System] Shutting down...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RECELL-AI Controller")
    parser.add_argument('--sim', action='store_true', help='Run without STM32 connected')
    parser.add_argument('--mock-ai', action='store_true', help='Run without YOLO/Camera')
    args = parser.parse_args()
    
    app = RecellMaster(simulate=args.sim, mock_ai=args.mock_ai)
    app.run()
