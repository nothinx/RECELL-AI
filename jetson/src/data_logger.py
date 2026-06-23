"""CSV logging for RECELL-AI grading sessions.

Two outputs per session:
- grading_log.csv      : one row per battery (aggregate metrics, decision, ground truth)
- discharge_curve.csv  : time-series samples captured during the constant-current load test

Both files share `battery_id` so the curves can be joined back to grade outcomes.
"""

import csv
import os
import threading
from collections import Counter
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

# Operator audit trail: who-changed-what-when (calibration, manual overrides).
EVENT_COLUMNS = ["timestamp", "event", "detail"]


class DataLogger:
    def __init__(self, output_dir="data/logs"):
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir
        self.grading_path = os.path.join(output_dir, "grading_log.csv")
        self.discharge_path = os.path.join(output_dir, "discharge_curve.csv")
        self.events_path = os.path.join(output_dir, "events_log.csv")
        self._lock = threading.Lock()
        self._ensure_header(self.grading_path, GRADING_COLUMNS)
        self._ensure_header(self.discharge_path, DISCHARGE_COLUMNS)
        self._ensure_header(self.events_path, EVENT_COLUMNS)

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

    def log_event(self, event, detail=""):
        """Audit trail entry (calibration change, manual override, etc.)."""
        ts = datetime.now().isoformat(timespec="seconds")
        with self._lock, open(self.events_path, "a", newline="") as f:
            csv.writer(f).writerow([ts, event, detail])

    def read_stats(self):
        """Aggregate grading_log.csv for the production dashboard. Returns
        {total, today, grades:{A,B,R,...}, avg_cycle_s, last_ts}. Tolerant of a
        missing/partial file (returns zeros)."""
        total = 0
        today = 0
        grades = Counter()
        cycle_sum = 0.0
        cycle_n = 0
        last_ts = ""
        today_str = datetime.now().date().isoformat()
        try:
            with open(self.grading_path, newline="") as f:
                for row in csv.DictReader(f):
                    total += 1
                    g = (row.get("grade_predicted") or "?").strip() or "?"
                    grades[g] += 1
                    ts = row.get("timestamp", "")
                    if ts:
                        last_ts = ts
                        if ts[:10] == today_str:
                            today += 1
                    try:
                        cycle_sum += float(row.get("cycle_time_s") or 0)
                        cycle_n += 1
                    except ValueError:
                        pass
        except FileNotFoundError:
            pass
        return {
            "total": total,
            "today": today,
            "grades": dict(grades),
            "avg_cycle_s": round(cycle_sum / cycle_n, 1) if cycle_n else 0.0,
            "last_ts": last_ts,
        }
