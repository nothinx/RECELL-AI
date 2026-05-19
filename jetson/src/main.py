import cv2
import serial
import threading
import time
import json
import argparse
import sys

# Default Configuration
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
MODEL_PATH = 'models/recell_yolo_v8n.engine'

class RecellMaster:
    def __init__(self, simulate=False, mock_ai=False):
        self.simulate = simulate
        self.mock_ai = mock_ai
        self.running = True
        self.ser = None
        
        self.grade_decision = None
        self.vision_score = 1.0
        self.electrical_data = {"soh": 0, "ir": 0}

        print("=== RECELL-AI Master Controller ===")
        print(f"Simulation Mode : {self.simulate}")
        print(f"Mock AI Mode    : {self.mock_ai}")
        print("===================================")

        # 1. Initialize Vision
        if not self.mock_ai:
            try:
                from ultralytics import YOLO
                print(f"[AI] Loading YOLO model: {MODEL_PATH}")
                self.model = YOLO(MODEL_PATH, task='detect')
            except Exception as e:
                print(f"[AI] Failed to load YOLO: {e}. Falling back to MOCK_AI.")
                self.mock_ai = True

        # 2. Initialize Communication
        if not self.simulate:
            try:
                self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
                print(f"[Comm] Connected to STM32 on {SERIAL_PORT}")
            except Exception as e:
                print(f"[Comm] Error connecting to Serial: {e}. Falling back to SIMULATION.")
                self.simulate = True

    def vision_thread(self):
        """Asynchronous vision processing loop."""
        if self.mock_ai:
            while self.running:
                time.sleep(1) # Mock vision delay
            return

        cap = cv2.VideoCapture(0)
        while self.running:
            ret, frame = cap.read()
            if not ret: continue
            
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
        """Asynchronous serial data receiver."""
        while self.running:
            if not self.simulate and self.ser and self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8').strip()
                try:
                    data = json.loads(line)
                    print(f"\r[STM32] {data}\nCMD> ", end="")
                    if "soh" in data:
                        self.electrical_data["soh"] = data["soh"]
                except:
                    print(f"\r[STM32 Raw] {line}\nCMD> ", end="")
            time.sleep(0.01)

    def send_command(self, cmd, params=None):
        """Send structured command to STM32."""
        packet = {"cmd": cmd}
        if params: packet.update(params)
        payload = json.dumps(packet) + '\n'
        
        if self.simulate:
            print(f"\n[Simulate-TX] {payload.strip()}")
        else:
            if self.ser: self.ser.write(payload.encode())

    def calculate_final_grade(self):
        soh = self.electrical_data.get("soh", 0)
        if self.vision_score < 0.4 or soh < 60: return "R"
        elif self.vision_score > 0.8 and soh > 80: return "A"
        else: return "B"

    def interactive_cli(self):
        """CLI for testing actuators manually."""
        print("\n--- Hardware Test Menu ---")
        print("1: Test Conveyor")
        print("2: Stop Conveyor")
        print("3: Test Stepper (Sort)")
        print("4: Test Load (CC)")
        print("5: Full Automated Cycle")
        print("q: Quit")
        
        while self.running:
            try:
                choice = input("CMD> ").strip()
                if choice == '1': self.send_command("TEST_CONVEYOR")
                elif choice == '2': self.send_command("STOP_CONVEYOR")
                elif choice == '3': self.send_command("TEST_STEPPER")
                elif choice == '4': self.send_command("TEST_LOAD")
                elif choice == '5':
                    print("[Auto] Starting Cycle...")
                    self.send_command("MOVE_CONVEYOR", {"dist": 50})
                    time.sleep(2)
                    self.send_command("START_SOH")
                    time.sleep(2)
                    grade = self.calculate_final_grade()
                    self.send_command("SORT", {"grade": grade})
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
