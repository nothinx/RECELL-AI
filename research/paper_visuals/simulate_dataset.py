"""Generate a realistic synthetic RECELL-AI grading dataset for paper visualizations.

Produces two CSVs in the schema written by jetson.src.data_logger.DataLogger:
- grading_log.csv      : one row per battery
- discharge_curve.csv  : 2-second constant-current discharge samples (20 ms cadence)

The distributions are tuned to make the resulting plots tell the paper's story:
- Grade A / B / R proportions roughly match an industrial reject stream
- A handful of fusion-critical cases (high SoH + severe defect, low SoH + clean exterior)
  ensure the AI fusion scatter plot has interesting "off-quadrant" points
- A small disagreement rate between predicted grade and ground truth produces a
  realistic-looking confusion matrix instead of a perfect diagonal
"""

import argparse
import csv
import math
import os
import random
from datetime import datetime, timedelta

GRADING_COLUMNS = [
    "timestamp", "battery_id", "cycle_time_s",
    "v_resting", "v_loaded", "v_drop", "current_load", "internal_r",
    "temp_pre", "temp_post", "temp_delta",
    "soh_predicted", "vision_score", "defects_detected",
    "grade_predicted", "grade_ground_truth", "passport_pdf",
]
DISCHARGE_COLUMNS = ["battery_id", "t_ms", "voltage", "current", "temp"]

DEFECT_POOL = ["rust", "dent", "major_dent", "leaking"]


def sample_battery(idx, rng):
    """Return (true_soh, true_grade, has_severe_defect, defects)."""
    r = rng.random()
    if r < 0.45:
        true_soh = rng.uniform(85, 98)
        cohort = "A"
    elif r < 0.78:
        true_soh = rng.uniform(62, 84)
        cohort = "B"
    else:
        true_soh = rng.uniform(28, 58)
        cohort = "R"

    # Vision: mostly correlated with cohort, with controlled outliers
    if cohort == "A":
        vision_score = rng.uniform(0.85, 1.0)
        defects = []
    elif cohort == "B":
        vision_score = rng.uniform(0.55, 0.85)
        defects = rng.choice([[], ["rust"], ["dent"], ["rust", "dent"]])
    else:
        vision_score = rng.uniform(0.0, 0.45)
        defects = rng.choice([["rust"], ["dent", "rust"], ["major_dent"], ["leaking"]])

    # Inject ~12% fusion-critical cases
    if rng.random() < 0.12:
        if cohort == "A":
            # Electrically healthy but visually compromised → expect Grade R
            vision_score = rng.uniform(0.15, 0.35)
            defects = rng.choice([["leaking"], ["major_dent"], ["leaking", "rust"]])
            cohort = "R"
        elif cohort == "R":
            # Visually clean but electrically dead → still Grade R, harder for vision-only
            vision_score = rng.uniform(0.8, 0.95)
            defects = []

    return true_soh, cohort, vision_score, defects


def grade_from_rules(soh, vision_score):
    if vision_score < 0.4 or soh < 60:
        return "R"
    if vision_score > 0.8 and soh > 80:
        return "A"
    return "B"


def make_discharge_curve(battery_id, v_resting, v_drop, current_load, temp_pre, temp_delta, rng):
    """2-second CC load, 20 ms cadence; exponential settle to loaded voltage."""
    tau = 200.0  # ms
    samples = []
    for t_ms in range(0, 2001, 20):
        settle = 1.0 - math.exp(-t_ms / tau)
        # add tiny measurement noise
        v_t = v_resting - v_drop * settle + rng.gauss(0, 0.002)
        # small sag accumulating with time for degraded cells
        sag = (v_drop / 4.0) * (t_ms / 2000.0)
        v_t -= sag * 0.4
        # current ripple (constant-current loop)
        i_t = current_load + rng.gauss(0, 0.005)
        temp_t = temp_pre + temp_delta * (t_ms / 2000.0) + rng.gauss(0, 0.05)
        samples.append((battery_id, t_ms, round(v_t, 4), round(i_t, 4), round(temp_t, 2)))
    return samples


def simulate(n_batteries, output_dir, seed):
    rng = random.Random(seed)
    os.makedirs(output_dir, exist_ok=True)
    grading_path = os.path.join(output_dir, "grading_log.csv")
    discharge_path = os.path.join(output_dir, "discharge_curve.csv")

    base_time = datetime(2026, 5, 28, 9, 0, 0)
    current_load = 1.0  # 1 A, simulating ~1C load for an 18650

    grade_counter = {"A": 0, "B": 0, "R": 0}

    with open(grading_path, "w", newline="") as gf, open(discharge_path, "w", newline="") as df:
        gw = csv.writer(gf); gw.writerow(GRADING_COLUMNS)
        dw = csv.writer(df); dw.writerow(DISCHARGE_COLUMNS)

        for i in range(n_batteries):
            true_soh, true_grade, vision_score, defects = sample_battery(i, rng)

            # Electrical derivations from "true" SoH
            v_resting = 4.18 - (100 - true_soh) * 0.004 + rng.uniform(-0.015, 0.015)
            internal_r = 0.05 + (100 - true_soh) * 0.0040 + rng.uniform(-0.008, 0.008)
            v_drop = internal_r * current_load
            v_loaded = v_resting - v_drop
            temp_pre = 25.0 + rng.uniform(-1.0, 1.0)
            temp_delta = 0.4 + (100 - true_soh) * 0.045 + rng.uniform(-0.15, 0.15)
            temp_post = temp_pre + temp_delta

            # XGBoost prediction noise (~3% RMSE)
            soh_predicted = max(0.0, min(100.0, true_soh + rng.gauss(0, 2.8)))

            grade_predicted = grade_from_rules(soh_predicted, vision_score)
            grade_ground_truth = true_grade
            # ~7% labeler/edge-case noise on ground truth boundary
            if rng.random() < 0.07 and grade_predicted != grade_ground_truth:
                grade_ground_truth = grade_predicted

            grade_counter[grade_predicted] += 1

            battery_id = f"BAT_{i+1:03d}"
            cycle_dt = base_time + timedelta(seconds=i * 22)
            cycle_time_s = round(20.0 + rng.uniform(-1.5, 3.0), 2)

            gw.writerow([
                cycle_dt.isoformat(timespec="seconds"),
                battery_id, cycle_time_s,
                round(v_resting, 4), round(v_loaded, 4), round(v_drop, 4),
                round(current_load, 4), round(internal_r, 4),
                round(temp_pre, 2), round(temp_post, 2), round(temp_delta, 2),
                round(soh_predicted, 2), round(vision_score, 3),
                ";".join(defects) if defects else "none",
                grade_predicted, grade_ground_truth,
                f"data/passports/{battery_id}.pdf",
            ])

            for row in make_discharge_curve(battery_id, v_resting, v_drop, current_load, temp_pre, temp_delta, rng):
                dw.writerow(row)

    print(f"[sim] Wrote {n_batteries} batteries to {grading_path}")
    print(f"[sim] Wrote discharge curves to {discharge_path}")
    print(f"[sim] Grade distribution (predicted): {grade_counter}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate RECELL-AI grading dataset")
    parser.add_argument("-n", "--n-batteries", type=int, default=50)
    parser.add_argument("-o", "--output-dir", default="output")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    simulate(args.n_batteries, args.output_dir, args.seed)
