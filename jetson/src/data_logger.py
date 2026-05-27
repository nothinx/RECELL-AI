"""CSV logging for RECELL-AI grading sessions.

Two outputs per session:
- grading_log.csv      : one row per battery (aggregate metrics, decision, ground truth)
- discharge_curve.csv  : time-series samples captured during the constant-current load test

Both files share `battery_id` so the curves can be joined back to grade outcomes.
"""

import csv
import os
import threading
from datetime import datetime

GRADING_COLUMNS = [
    "timestamp",
    "battery_id",
    "cycle_time_s",
    "v_resting",
    "v_loaded",
    "v_drop",
    "current_load",
    "internal_r",
    "temp_pre",
    "temp_post",
    "temp_delta",
    "soh_predicted",
    "vision_score",
    "defects_detected",
    "grade_predicted",
    "grade_ground_truth",
    "passport_pdf",
]

DISCHARGE_COLUMNS = ["battery_id", "t_ms", "voltage", "current", "temp"]


class DataLogger:
    def __init__(self, output_dir="data/logs"):
        os.makedirs(output_dir, exist_ok=True)
        self.grading_path = os.path.join(output_dir, "grading_log.csv")
        self.discharge_path = os.path.join(output_dir, "discharge_curve.csv")
        self._lock = threading.Lock()
        self._ensure_header(self.grading_path, GRADING_COLUMNS)
        self._ensure_header(self.discharge_path, DISCHARGE_COLUMNS)

    @staticmethod
    def _ensure_header(path, columns):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(columns)

    def log_grading(self, **fields):
        fields.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        row = [fields.get(c, "") for c in GRADING_COLUMNS]
        with self._lock, open(self.grading_path, "a", newline="") as f:
            csv.writer(f).writerow(row)

    def log_discharge_sample(self, battery_id, t_ms, voltage, current, temp):
        with self._lock, open(self.discharge_path, "a", newline="") as f:
            csv.writer(f).writerow([battery_id, t_ms, voltage, current, temp])

    def log_discharge_batch(self, battery_id, samples):
        """samples: iterable of (t_ms, voltage, current, temp) tuples."""
        with self._lock, open(self.discharge_path, "a", newline="") as f:
            w = csv.writer(f)
            for t_ms, v, i, t in samples:
                w.writerow([battery_id, t_ms, v, i, t])
