"""Unit test DataLogger: agregasi statistik + audit event. Stdlib only —
jalan tanpa pytest via blok __main__ (DataLogger tak butuh hardware)."""
import sys
import csv
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jetson" / "src"))
from data_logger import DataLogger  # noqa: E402


def _seed_grading(path, rows):
    cols = ["timestamp", "battery_id", "cycle_time_s", "grade_predicted"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "battery_id", "cycle_time_s", "v_resting",
                    "v_loaded", "v_drop", "current_load", "internal_r",
                    "temp_pre", "temp_post", "temp_delta", "soh_predicted",
                    "vision_score", "defects_detected", "grade_predicted",
                    "grade_ground_truth", "passport_pdf"])
        for ts, bid, ct, g in rows:
            r = {c: "" for c in range(17)}
            line = [ts, bid, ct] + [""] * 11 + [g, "", ""]
            w.writerow(line)


def test_read_stats_aggregates():
    with tempfile.TemporaryDirectory() as d:
        dl = DataLogger(output_dir=d)
        today = datetime.now().date().isoformat()
        _seed_grading(dl.grading_path, [
            (f"{today}T08:00:00", "RC-1", "10.0", "A"),
            (f"{today}T08:01:00", "RC-2", "12.0", "B"),
            ("2020-01-01T00:00:00", "RC-3", "20.0", "R"),
            (f"{today}T08:02:00", "RC-4", "14.0", "A"),
        ])
        s = dl.read_stats()
        assert s["total"] == 4, s
        assert s["today"] == 3, s            # 3 baris bertanggal hari ini
        assert s["grades"]["A"] == 2, s
        assert s["grades"]["B"] == 1, s
        assert s["grades"]["R"] == 1, s
        assert s["avg_cycle_s"] == 14.0, s   # (10+12+20+14)/4
        assert s["last_ts"].startswith(today)


def test_read_stats_missing_file():
    with tempfile.TemporaryDirectory() as d:
        dl = DataLogger(output_dir=d)
        import os
        os.remove(dl.grading_path)           # hapus -> harus aman, nol semua
        s = dl.read_stats()
        assert s == {"total": 0, "today": 0, "grades": {},
                     "avg_cycle_s": 0.0, "last_ts": ""}, s


def test_log_event_appends_row():
    with tempfile.TemporaryDirectory() as d:
        dl = DataLogger(output_dir=d)
        dl.log_event("CALIB_CHANGE", "step_pulse_us:50->400")
        dl.log_event("GRADE_OVERRIDE", "RC-9: A->R")
        with open(dl.events_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2, rows
        assert rows[0]["event"] == "CALIB_CHANGE"
        assert rows[1]["detail"] == "RC-9: A->R"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("OK DataLogger")
