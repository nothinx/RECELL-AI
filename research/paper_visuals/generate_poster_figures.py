"""Generate POSTER-GRADE visualizations for RECELL-AI (KIWIE 2026).

Produces a cohesive, branded set of 300 DPI figures from the grading dataset
(grading_log.csv + discharge_curve.csv). Designed to look professional when
dropped into an A0 poster, scientific paper, or pitch deck.

Usage:
    python generate_poster_figures.py --data poster_data --out poster_figures

Figures:
    fig1_grade_distribution.png   throughput / sorting outcome (bar + %)
    fig2_ai_fusion_scatter.png    THE key plot: shaded multimodal decision map
    fig3_discharge_curve.png      mean +/- band CC discharge per grade
    fig4_confusion_matrix.png     predicted vs ground truth (+ accuracy)
    fig5_soh_distribution.png     SoH spread per grade (box + points)
    fig6_resistance_vs_soh.png    internal resistance vs SoH (physics validation)
    fig7_performance_scorecard.png headline KPI infographic
"""

import argparse
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Rectangle, FancyArrowPatch
from matplotlib.lines import Line2D
import seaborn as sns
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
    accuracy_score,
)

# --------------------------------------------------------------------------- #
# Branding / theme
# --------------------------------------------------------------------------- #
INK = "#1f2937"          # near-black slate for text
MUTED = "#6b7280"        # muted grey
GRID = "#e5e7eb"         # light grid
ACCENT = "#0e7490"       # RECELL teal accent

GRADE_COLOR = {"A": "#16a34a", "B": "#f59e0b", "R": "#dc2626"}   # solid
GRADE_FILL = {"A": "#bbf7d0", "B": "#fde68a", "R": "#fecaca"}    # light regions
GRADE_LABEL = {"A": "Grade A  (Reusable)", "B": "Grade B  (Refurbish)", "R": "Grade R  (Recycle)"}
ORDER = ["A", "B", "R"]


def apply_theme():
    sns.set_theme(style="white")
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": MUTED,
        "axes.linewidth": 1.1,
        "axes.titlesize": 17,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.labelsize": 13,
        "axes.labelweight": "medium",
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "font.size": 12,
        "legend.frameon": False,
        "legend.fontsize": 11,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.9,
    })
    # Prefer a clean sans font if present
    for fam in ["Segoe UI", "Arial", "DejaVu Sans"]:
        if any(fam.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = fam
            break


def brand(ax, tag="RECELL-AI"):
    """Small watermark tag bottom-right of an axes' figure."""
    ax.figure.text(0.995, 0.005, tag, ha="right", va="bottom",
                   fontsize=9, color=MUTED, style="italic")


def savefig(fig, out_dir, name):
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  - {name}")


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def fig_grade_distribution(df, out_dir):
    counts = df["grade_predicted"].value_counts().reindex(ORDER).fillna(0).astype(int)
    total = counts.sum()
    fig, ax = plt.subplots(figsize=(8.2, 6))
    bars = ax.bar(
        [GRADE_LABEL[g] for g in ORDER], counts.values,
        color=[GRADE_COLOR[g] for g in ORDER], width=0.62,
        edgecolor="white", linewidth=2, zorder=3,
    )
    ax.set_axisbelow(True)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Number of Batteries")
    ax.set_title("Automated Sorting Outcome", pad=14)
    ax.set_ylim(0, counts.max() * 1.18)
    for g, b in zip(ORDER, bars):
        pct = counts[g] / total * 100
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + total * 0.012,
                f"{counts[g]}\n{pct:.0f}%", ha="center", va="bottom",
                fontsize=12.5, fontweight="bold", color=INK)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    brand(ax)
    savefig(fig, out_dir, "fig1_grade_distribution.png")


def fig_fusion_scatter(df, out_dir):
    SOH_R, SOH_A = 60, 80
    VIS_R, VIS_A = 0.40, 0.80
    fig, ax = plt.subplots(figsize=(10, 7.2))

    # Decision regions (drawn as background patches)
    ax.add_patch(Rectangle((0, 0), 105, 1.05, facecolor=GRADE_FILL["B"], alpha=0.45, zorder=0))
    # R region: SoH < 60 (full height) + Vision < 0.4 (full width)
    ax.add_patch(Rectangle((0, 0), SOH_R, 1.05, facecolor=GRADE_FILL["R"], alpha=0.55, zorder=1))
    ax.add_patch(Rectangle((0, 0), 105, VIS_R, facecolor=GRADE_FILL["R"], alpha=0.55, zorder=1))
    # A region: SoH > 80 AND Vision > 0.8
    ax.add_patch(Rectangle((SOH_A, VIS_A), 105 - SOH_A, 1.05 - VIS_A,
                           facecolor=GRADE_FILL["A"], alpha=0.6, zorder=1))

    for g in ORDER:
        sub = df[df.grade_predicted == g]
        ax.scatter(sub.soh_predicted, sub.vision_score, s=95,
                   color=GRADE_COLOR[g], edgecolor="white", linewidth=1.1,
                   alpha=0.95, zorder=4, label=GRADE_LABEL[g])

    # Threshold lines
    for x in (SOH_R, SOH_A):
        ax.axvline(x, color=MUTED, ls="--", lw=1.1, alpha=0.7, zorder=3)
    for y in (VIS_R, VIS_A):
        ax.axhline(y, color=MUTED, ls="--", lw=1.1, alpha=0.7, zorder=3)

    ax.set_xlim(0, 105)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Electrical Health  —  Predicted SoH (%)   [XGBoost]")
    ax.set_ylabel("Physical Integrity  —  Vision Score   [YOLOv8n]")
    ax.set_title("Multimodal AI Fusion Decision Map", pad=14)
    ax.legend(loc="lower right", framealpha=0.95, frameon=True,
              edgecolor=GRID, facecolor="white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    brand(ax)
    savefig(fig, out_dir, "fig2_ai_fusion_scatter.png")


def fig_discharge_curve(df_log, df_curves, out_dir):
    if df_curves.empty:
        print("  [!] no discharge curve data, skipping fig3")
        return
    merged = df_curves.merge(df_log[["battery_id", "grade_predicted"]],
                             on="battery_id", how="left")
    fig, ax = plt.subplots(figsize=(10, 6.2))
    for g in ORDER:
        sub = merged[merged.grade_predicted == g]
        if sub.empty:
            continue
        stats = sub.groupby("t_ms").voltage.agg(["mean", "std"]).reset_index()
        t = stats.t_ms
        ax.fill_between(t, stats["mean"] - stats["std"], stats["mean"] + stats["std"],
                        color=GRADE_COLOR[g], alpha=0.18, zorder=2)
        ax.plot(t, stats["mean"], color=GRADE_COLOR[g], lw=2.6,
                label=GRADE_LABEL[g], zorder=3)

    ax.set_xlabel("Time under load (ms)")
    ax.set_ylabel("Terminal Voltage (V)")
    ax.set_title("Constant-Current (1 A) Discharge Signature per Grade", pad=14)
    ax.legend(loc="upper right", framealpha=0.95, frameon=True,
              edgecolor=GRID, facecolor="white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    brand(ax)
    savefig(fig, out_dir, "fig3_discharge_curve.png")


def fig_confusion_matrix(df, out_dir):
    df_eval = df[df.grade_ground_truth.isin(ORDER)]
    if df_eval.empty:
        print("  [!] no ground truth, skipping fig4")
        return
    cm = confusion_matrix(df_eval.grade_ground_truth, df_eval.grade_predicted, labels=ORDER)
    acc = accuracy_score(df_eval.grade_ground_truth, df_eval.grade_predicted) * 100
    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="BuGn", square=True,
                xticklabels=[f"Grade {g}" for g in ORDER],
                yticklabels=[f"Grade {g}" for g in ORDER],
                cbar=False, annot_kws={"size": 20, "weight": "bold"},
                linewidths=2, linecolor="white", ax=ax)
    ax.set_xlabel("Predicted Grade")
    ax.set_ylabel("Ground Truth")
    ax.set_title(f"Grading Confusion Matrix  —  Accuracy {acc:.1f}%", pad=14)
    ax.tick_params(length=0)
    brand(ax)
    savefig(fig, out_dir, "fig4_confusion_matrix.png")


def fig_soh_distribution(df, out_dir):
    fig, ax = plt.subplots(figsize=(8.2, 6))
    sns.boxplot(x="grade_predicted", y="soh_predicted", data=df, order=ORDER,
                hue="grade_predicted", hue_order=ORDER, palette=GRADE_COLOR,
                width=0.55, fliersize=0, legend=False,
                boxprops=dict(alpha=0.85), ax=ax)
    sns.stripplot(x="grade_predicted", y="soh_predicted", data=df, order=ORDER,
                  color=INK, alpha=0.45, size=4, jitter=0.18, ax=ax)
    ax.set_xticks(range(len(ORDER)))
    ax.axhline(80, color=GRADE_COLOR["A"], ls="--", lw=1.2, alpha=0.7)
    ax.axhline(60, color=GRADE_COLOR["R"], ls="--", lw=1.2, alpha=0.7)
    ax.set_xticklabels([GRADE_LABEL[g] for g in ORDER])
    ax.set_xlabel("")
    ax.set_ylabel("Predicted State of Health (%)")
    ax.set_title("State-of-Health Spread per Grade", pad=14)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    brand(ax)
    savefig(fig, out_dir, "fig5_soh_distribution.png")


def fig_resistance_vs_soh(df, out_dir):
    fig, ax = plt.subplots(figsize=(9, 6.2))
    for g in ORDER:
        sub = df[df.grade_predicted == g]
        ax.scatter(sub.soh_predicted, sub.internal_r * 1000, s=80,
                   color=GRADE_COLOR[g], edgecolor="white", linewidth=1,
                   alpha=0.9, label=GRADE_LABEL[g], zorder=3)
    # Trend line
    x = df.soh_predicted.values
    y = (df.internal_r * 1000).values
    coef = np.polyfit(x, y, 1)
    xs = np.linspace(x.min(), x.max(), 100)
    ax.plot(xs, np.polyval(coef, xs), color=INK, ls="--", lw=1.8, zorder=4,
            label=f"Linear fit  (r = {np.corrcoef(x, y)[0,1]:.2f})")
    ax.set_xlabel("Predicted State of Health (%)")
    ax.set_ylabel("Internal Resistance (mΩ)")
    ax.set_title("Electrical Physics Validation: Resistance vs SoH", pad=14)
    ax.legend(loc="upper right", framealpha=0.95, frameon=True,
              edgecolor=GRID, facecolor="white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    brand(ax)
    savefig(fig, out_dir, "fig6_resistance_vs_soh.png")


def fig_scorecard(df, out_dir):
    df_eval = df[df.grade_ground_truth.isin(ORDER)]
    acc = accuracy_score(df_eval.grade_ground_truth, df_eval.grade_predicted) * 100
    p, r, f1, _ = precision_recall_fscore_support(
        df_eval.grade_ground_truth, df_eval.grade_predicted,
        labels=ORDER, average="macro", zero_division=0)
    avg_cycle = df.cycle_time_s.mean()
    throughput = 3600 / avg_cycle
    total = len(df)

    fig, axes = plt.subplots(1, 4, figsize=(14, 3.4))
    cards = [
        (f"{acc:.1f}%", "Grading Accuracy", ACCENT),
        (f"{f1*100:.1f}%", "Macro F1-Score", GRADE_COLOR["A"]),
        (f"{throughput:.0f}", "Batteries / hour", GRADE_COLOR["B"]),
        (f"{avg_cycle:.1f}s", "Avg Cycle Time", "#7c3aed"),
    ]
    for ax, (big, small, col) in zip(axes, cards):
        ax.axis("off")
        ax.add_patch(Rectangle((0.04, 0.08), 0.92, 0.84, transform=ax.transAxes,
                               facecolor="white", edgecolor=GRID, lw=1.5,
                               zorder=1))
        ax.add_patch(Rectangle((0.04, 0.08), 0.92, 0.12, transform=ax.transAxes,
                               facecolor=col, edgecolor="none", zorder=2))
        ax.text(0.5, 0.60, big, ha="center", va="center", transform=ax.transAxes,
                fontsize=34, fontweight="bold", color=col)
        ax.text(0.5, 0.30, small, ha="center", va="center", transform=ax.transAxes,
                fontsize=13, color=INK, fontweight="medium")
    fig.suptitle("RECELL-AI  —  Headline Performance Metrics",
                 fontsize=18, fontweight="bold", color=INK, y=1.04)
    fig.text(0.5, -0.06, f"Macro precision {p*100:.1f}%  |  macro recall {r*100:.1f}%  "
             f"|  evaluated on n = {total} graded cells",
             ha="center", fontsize=10.5, color=MUTED)
    savefig(fig, out_dir, "fig7_performance_scorecard.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="poster_data", help="dir with grading_log.csv + discharge_curve.csv")
    ap.add_argument("--out", default="poster_figures")
    args = ap.parse_args()

    apply_theme()
    os.makedirs(args.out, exist_ok=True)
    df = pd.read_csv(os.path.join(args.data, "grading_log.csv"))
    curve_path = os.path.join(args.data, "discharge_curve.csv")
    curves = pd.read_csv(curve_path) if os.path.exists(curve_path) else pd.DataFrame()
    print(f"Loaded {len(df)} batteries, {len(curves)} discharge samples")
    print(f"Writing figures to {args.out}/ ...")

    fig_grade_distribution(df, args.out)
    fig_fusion_scatter(df, args.out)
    fig_discharge_curve(df, curves, args.out)
    fig_confusion_matrix(df, args.out)
    fig_soh_distribution(df, args.out)
    fig_resistance_vs_soh(df, args.out)
    fig_scorecard(df, args.out)
    print("Done.")


if __name__ == "__main__":
    main()
