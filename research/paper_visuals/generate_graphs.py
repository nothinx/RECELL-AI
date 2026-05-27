"""Generate paper/poster visualizations from RECELL-AI grading logs.

Reads two CSVs in the schema produced by `jetson/src/data_logger.py` and
`simulate_dataset.py`:
- output/grading_log.csv      (aggregate, one row per battery)
- output/discharge_curve.csv  (time-series samples during CC load test)

Outputs (300 DPI PNG) into output/:
- 01_grade_distribution.png   bar chart of sorted batteries
- 02_ai_fusion_scatter.png    Vision Score vs SoH coloured by predicted grade
- 03_discharge_curve.png      empirical CC discharge curves grouped by grade
- 04_confusion_matrix.png     predicted grade vs ground truth
- 05_soh_distribution.png     SoH distribution by grade (violin)
"""

import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report

plt.style.use('seaborn-v0_8-whitegrid')
sns.set_context("paper", font_scale=1.4)

OUTPUT_DIR = "output"
GRADE_PALETTE = {"A": "#2ecc71", "B": "#ffc107", "R": "#e74c3c"}
GRADE_ORDER = ["A", "B", "R"]


def load_data():
    log_path = os.path.join(OUTPUT_DIR, "grading_log.csv")
    curve_path = os.path.join(OUTPUT_DIR, "discharge_curve.csv")
    if not os.path.exists(log_path):
        print(f"[!] {log_path} not found. Run simulate_dataset.py first or copy real CSV here.")
        sys.exit(1)
    df = pd.read_csv(log_path)
    curves = pd.read_csv(curve_path) if os.path.exists(curve_path) else pd.DataFrame()
    return df, curves


def plot_grade_distribution(df):
    plt.figure(figsize=(8, 6))
    ax = sns.countplot(
        x="grade_predicted", data=df,
        palette=GRADE_PALETTE, order=GRADE_ORDER,
    )
    plt.title("Distribution of Sorted Batteries", fontweight="bold")
    plt.xlabel("Predicted Grade")
    plt.ylabel("Count")
    for p in ax.patches:
        ax.annotate(
            f"{int(p.get_height())}",
            (p.get_x() + p.get_width() / 2.0, p.get_height()),
            ha="center", va="bottom", fontsize=12, xytext=(0, 5),
            textcoords="offset points",
        )
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_grade_distribution.png"), dpi=300)
    plt.close()


def plot_fusion_scatter(df):
    plt.figure(figsize=(10, 7))
    sns.scatterplot(
        x="soh_predicted", y="vision_score", hue="grade_predicted",
        data=df, palette=GRADE_PALETTE, hue_order=GRADE_ORDER,
        s=110, alpha=0.85, edgecolor="black",
    )
    plt.axvline(x=60, color="red", linestyle="--", alpha=0.5, label="SOH Reject Threshold")
    plt.axvline(x=80, color="green", linestyle="--", alpha=0.5, label="SOH A-Grade Threshold")
    plt.axhline(y=0.4, color="red", linestyle=":", alpha=0.5, label="Vision Reject Threshold")
    plt.axhline(y=0.8, color="green", linestyle=":", alpha=0.5, label="Vision A-Grade Threshold")
    plt.title("AI Fusion Decision Mapping: Vision Score vs Electrical SoH", fontweight="bold")
    plt.xlabel("Predicted State of Health (SoH) %")
    plt.ylabel("Vision AI Score (Physical Integrity)")
    plt.xlim(0, 105)
    plt.ylim(-0.05, 1.05)
    plt.legend(bbox_to_anchor=(1.04, 1), loc="upper left", borderaxespad=0.0)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_ai_fusion_scatter.png"), dpi=300, bbox_inches="tight")
    plt.close()


def plot_discharge_curves(df_log, df_curves):
    if df_curves.empty:
        print("[!] No discharge_curve.csv — skipping discharge plot.")
        return
    merged = df_curves.merge(df_log[["battery_id", "grade_predicted"]], on="battery_id", how="left")

    plt.figure(figsize=(10, 6))
    for grade in GRADE_ORDER:
        sub = merged[merged.grade_predicted == grade]
        if sub.empty:
            continue
        sample_ids = sub.battery_id.drop_duplicates().sample(min(3, sub.battery_id.nunique()), random_state=1)
        for j, bid in enumerate(sample_ids):
            row = sub[sub.battery_id == bid]
            label = f"Grade {grade}" if j == 0 else None
            plt.plot(row.t_ms, row.voltage, color=GRADE_PALETTE[grade], alpha=0.75, linewidth=2, label=label)

    plt.title("Empirical Discharge Curves under 1 A Constant-Current Load", fontweight="bold")
    plt.xlabel("Time (ms)")
    plt.ylabel("Battery Voltage (V)")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_discharge_curve.png"), dpi=300)
    plt.close()


def plot_confusion_matrix(df):
    df_eval = df[df.grade_ground_truth.isin(GRADE_ORDER)]
    if df_eval.empty:
        print("[!] No ground_truth labels — skipping confusion matrix.")
        return
    cm = confusion_matrix(df_eval.grade_ground_truth, df_eval.grade_predicted, labels=GRADE_ORDER)
    accuracy = (cm.diagonal().sum() / cm.sum()) * 100

    plt.figure(figsize=(7, 6))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=[f"Grade {g}" for g in GRADE_ORDER],
        yticklabels=[f"Grade {g}" for g in GRADE_ORDER],
        cbar=False, annot_kws={"size": 16},
    )
    plt.title(f"Confusion Matrix (Overall Accuracy: {accuracy:.1f}%)", fontweight="bold")
    plt.xlabel("Predicted Grade")
    plt.ylabel("Ground Truth")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "04_confusion_matrix.png"), dpi=300)
    plt.close()

    print("\n=== Classification Report ===")
    print(classification_report(df_eval.grade_ground_truth, df_eval.grade_predicted, labels=GRADE_ORDER, zero_division=0))


def plot_soh_distribution(df):
    plt.figure(figsize=(8, 6))
    sns.violinplot(
        x="grade_predicted", y="soh_predicted", data=df,
        palette=GRADE_PALETTE, order=GRADE_ORDER, inner="quartile",
    )
    sns.stripplot(
        x="grade_predicted", y="soh_predicted", data=df,
        order=GRADE_ORDER, color="black", alpha=0.5, size=3,
    )
    plt.title("Predicted SoH Distribution per Grade", fontweight="bold")
    plt.xlabel("Predicted Grade")
    plt.ylabel("State of Health (%)")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "05_soh_distribution.png"), dpi=300)
    plt.close()


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Loading grading dataset...")
    df, curves = load_data()
    print(f"- {len(df)} batteries, {len(curves)} discharge samples")

    plot_grade_distribution(df)
    print("- 01_grade_distribution.png")

    plot_fusion_scatter(df)
    print("- 02_ai_fusion_scatter.png")

    plot_discharge_curves(df, curves)
    print("- 03_discharge_curve.png")

    plot_confusion_matrix(df)
    print("- 04_confusion_matrix.png")

    plot_soh_distribution(df)
    print("- 05_soh_distribution.png")

    print(f"\nAll graphs (300 DPI) saved to '{OUTPUT_DIR}/'.")
