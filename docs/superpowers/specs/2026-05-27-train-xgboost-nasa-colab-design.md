# Spec: `Train_XGBoost_NASA.ipynb` (Google Colab)

**Date:** 2026-05-27
**Status:** Approved, ready for implementation
**Replaces:** `jetson/notebooks/Train_XGBoost_NASA.ipynb` (current file is mock-data skeleton)

## Goal

Train a production-grade XGBoost regressor for State-of-Health (SoH) prediction on the real NASA Battery Dataset, exporting a `soh_xgb_model.json` that drops directly into `jetson/src/main.py` (line 55 `xgb_model.load_model(...)`).

## Dataset

- **Source:** [`patrickfleith/nasa-battery-dataset`](https://www.kaggle.com/datasets/patrickfleith/nasa-battery-dataset) version 2 (Kaggle)
- **Format:** cleaned CSV — `cleaned_dataset/metadata.csv` (one row per cycle) + `cleaned_dataset/data/<filename>.csv` (time-series per cycle, named by `uid`)
- **Metadata columns used:** `battery_id`, `type` (filter `'discharge'`), `Capacity`, `filename`, `test_id`
- **Per-cycle CSV columns used:** `Voltage_measured`, `Current_measured`, `Temperature_measured`
- **Batteries:** B0005, B0006, B0007, B0018 (4 cells)
- **Access:** `kagglehub.dataset_download(...)` after user pastes Kaggle API token via `getpass` (new `KAGGLE_API_TOKEN=KGAT_...` format)

The dataset IS the output of Patrick Fleith's cleaning kernel (`patrickfleith/nasa-battery-life-prediction-dataset-cleaning`) — the kernel reads raw NASA `.mat` files from a different upload and writes cleaned CSVs. We consume the cleaned CSVs directly; no `.mat` parsing or kernel pulling needed.

## Feature Contract (locked)

Must match `jetson/src/main.py:140` exactly:

| Feature        | Formula (per discharge cycle)       |
|----------------|--------------------------------------|
| `v_drop`       | `max(V_measured) - min(V_measured)` |
| `internal_r`   | `v_drop / abs(min(I_measured))`     |
| `temp_delta`   | `max(T_measured) - T_measured[0]`   |

Target: `soh = clip((Capacity / 2.0) * 100, 0, 100)` (nominal 2.0 Ah, consistent with `jetson/scripts/parse_nasa_mat.py:58`).

## Evaluation Strategy

**Leave-One-Battery-Out cross-validation** via `GroupKFold(n_splits=4, groups=battery_id)`. Reports per-fold RMSE & MAE plus average. This is more honest than random split because production sees unseen battery brands.

After CV, retrain on **all 4 batteries** to produce the final exported model.

## Model

`xgb.XGBRegressor(objective='reg:squarederror', n_estimators=200, learning_rate=0.05, max_depth=5, subsample=0.8, random_state=42)`

No hyperparameter search (overkill for 3 features). Can be added later if RMSE > 5%.

## Notebook Structure (8 cells)

1. Install deps (`xgboost`, `scikit-learn`, `matplotlib`, `seaborn`, `kagglehub`)
2. Auth Kaggle — `getpass` prompt for `KAGGLE_API_TOKEN` (token starts with `KGAT_`); stored in env + `~/.kaggle/access_token` (600)
3. Download dataset via `kagglehub`, load `cleaned_dataset/metadata.csv`, filter to 4 target batteries
4. Load per-cycle CSVs (filter discharge + non-null Capacity), build `cycles_raw` with V/I/T arrays per cycle
5. Feature engineering: per-cycle `v_drop`, `internal_r`, `temp_delta`
6. EDA: SoH-vs-cycle line plots, feature distributions, correlation heatmap
7. Train + evaluate: GroupKFold loop, report metrics, plot pred-vs-actual
8. Final train + export: full-data retrain → `soh_xgb_model.json` → feature-importance plot → `files.download()`

## Robustness Rules

- Skip cycles with `len(voltages) < 10`
- Skip cycles with `i_max == 0` (avoid div-by-zero)
- `np.clip(soh, 0, 100)` on output
- Auto-detect `cleaned_dataset/data/` path (kagglehub returns parent dir)

## Deliverables

- Updated `jetson/notebooks/Train_XGBoost_NASA.ipynb`
- Output artifact: `soh_xgb_model.json` (downloads automatically in Colab)

## Out of Scope

- Hyperparameter tuning (GridSearch/Optuna)
- Random Forest baseline comparison
- Extended features (cycle_count, discharge_time, voltage_slope) — requires STM32 firmware changes
- Deep learning approaches (LSTM/Transformer)
