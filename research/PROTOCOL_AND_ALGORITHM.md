# RECELL-AI Communication Protocol & Algorithm Specification

**Version:** 1.0 (Mature Draft)
**Interface:** USB-Serial (115200 bps)
**Format:** Line-terminated JSON

---

## 1. Communication Protocol (JSON Schema)

### 1.1. Jetson to STM32 (Commands)
The Master (Jetson) controls the process flow.

| Command | Parameters | Description |
| :--- | :--- | :--- |
| `PING` | None | Heartbeat/Connectivity check. |
| `START_SOH` | `{"duration": 5000}` | Triggers CC Load measurement for X ms. |
| `MOVE_CONVEYOR` | `{"dir": 1, "dist": 100}` | Moves conveyor belt. |
| `SORT` | `{"grade": "A" \| "B" \| "R"}` | Triggers sorting stepper to specific bin. |
| `RESET` | None | Resets STM32 state machine. |

**Example:** `{"cmd": "SORT", "grade": "A"}\n`

### 1.2. STM32 to Jetson (Telemetry & Events)
The Slave (STM32) reports measurements and completion status.

| Event Type | Fields | Description |
| :--- | :--- | :--- |
| `STATUS` | `{"state": "IDLE" \| "BUSY" \| "ERROR"}` | Current STM32 status. |
| `MEASUREMENT` | `{"v": 3.72, "i": 1.05, "t": 32.5}` | Real-time V, I, and Temperature. |
| `SOH_RESULT` | `{"soh": 85.2, "internal_r": 0.12}` | Final calculated electrical health. |
| `DONE` | `{"op": "SORT" \| "MEASURE"}` | Confirmation of task completion. |

**Example:** `{"type": "MEASUREMENT", "v": 3.8, "i": 1.0}\n`

---

## 2. Grading Algorithm Structure (Multi-Modal)

The final decision is a fusion of **Computer Vision (CV)** and **Electrical Analysis (EA)**.

### 2.1. Vision Score (VS) - YOLOv8n
*   **Input:** Camera frames.
*   **Classes:** `normal`, `rust`, `dent`, `leaking`.
*   **Logic:** 
    *   If `leaking` or `major_dent` detected -> **Grade R (Reject)** immediately.
    *   If `rust` detected -> Penalty applied to Vision Score.

### 2.2. Electrical Score (ES) - Constant Current Load
*   **Method:** Discharging at 1C (approx 1-2A) for a short burst.
*   **Metric:** Voltage drop ($\Delta V$) used to calculate Internal Resistance ($R_i = \Delta V / I$).
*   **SoH Calculation:** Based on $R_i$ and Discharge Curve stability.

### 2.3. Final Grade Decision Table
| Vision Condition | SoH (Electrical) | Final Grade |
| :--- | :--- | :--- |
| Clean | > 80% | **Grade A** |
| Minor Rust/Dent | > 75% | **Grade B** |
| Clean | 60% - 80% | **Grade B** |
| Any Major Damage | Any | **Grade R (Recycle)** |
| Clean | < 60% | **Grade R (Recycle)** |

---

## 3. System State Machine (Combined)

1. **BOOT**: Jetson & STM32 handshake.
2. **FEEDING**: STM32 moves conveyor until IR/Proximity sensor triggers.
3. **INSPECTION_V**: Jetson runs YOLOv8n -> Saves VS.
4. **INSPECTION_E**: STM32 runs CC Load -> Sends ES to Jetson.
5. **DECISION**: Jetson calculates Final Grade.
6. **SORTING**: Jetson commands `SORT {grade}` -> STM32 moves Stepper.
7. **FINISH**: Log results to CSV/DB -> Repeat.
