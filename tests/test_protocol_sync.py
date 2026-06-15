"""Regresi kontrak protokol Jetson <-> STM32.

Mencegah salah satu sisi me-rename command/status/field tanpa sisi lain ikut.
Hanya pakai stdlib supaya bisa jalan di lingkungan minim (tanpa pytest pun bisa
via blok __main__ di bawah).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW = (ROOT / "firmware" / "RECELL_STM32" / "RECELL_STM32.ino").read_text(encoding="utf-8")
MAIN = (ROOT / "jetson" / "src" / "main.py").read_text(encoding="utf-8")
UI = (ROOT / "jetson" / "src" / "ui_dashboard.py").read_text(encoding="utf-8")
JETSON_TX = MAIN + "\n" + UI  # command sends may live in the controller OR the GUI layer

# --- Kontrak kanonik -------------------------------------------------------
COMMANDS = [
    "RESET", "MOVE_TO_PROX_1", "APPLY_SENSOR_AND_MEASURE",
    "MOVE_TO_PROX_2", "EJECT_A", "MOVE_TO_END", "STOP_CONVEYOR",
]
# Status yang dipancarkan firmware (semua), dan subset yang ditindaklanjuti Jetson.
STATUSES_EMITTED = [
    "BOOT_OK", "AT_PROX_1", "AT_PROX_2", "DISCHARGE_SAMPLE", "MEASUREMENT_DONE",
    "EJECTED_A", "DROPPED_B", "STOPPED", "RESET_OK", "EMERGENCY_STOP",
]
STATUSES_CONSUMED = [
    "MEASUREMENT_DONE", "DISCHARGE_SAMPLE", "AT_PROX_1", "AT_PROX_2",
    "EJECTED_A", "DROPPED_B", "EMERGENCY_STOP",
]
MEASUREMENT_FIELDS = ["volt", "curr", "v_resting", "temp_pre", "temp_post", "temp_delta"]
DISCHARGE_FIELDS = ["t_ms", "volt", "curr", "temp"]


def test_every_command_handled_by_firmware():
    for c in COMMANDS:
        assert re.search(rf'cmd\s*==\s*"{c}"', FW), f"firmware tak menangani command {c}"


def test_every_command_sent_by_jetson():
    for c in COMMANDS:
        assert re.search(rf'send_command\(\s*"{c}"', JETSON_TX), f"Jetson tak pernah kirim {c}"


def test_firmware_emits_all_statuses():
    for s in STATUSES_EMITTED:
        assert f'"{s}"' in FW, f"firmware tak memancarkan status {s}"


def test_jetson_consumes_expected_statuses():
    for s in STATUSES_CONSUMED:
        assert f'"{s}"' in MAIN, f"main.py tak menangani status {s}"


def test_measurement_fields_match_both_sides():
    for f in MEASUREMENT_FIELDS:
        assert f'"{f}"' in FW, f"firmware MEASUREMENT_DONE tak punya field {f}"
        assert f'"{f}"' in MAIN, f"main.py tak membaca field {f}"


def test_discharge_fields_match_both_sides():
    for f in DISCHARGE_FIELDS:
        assert f'"{f}"' in FW, f"firmware DISCHARGE_SAMPLE tak punya field {f}"
        assert f'"{f}"' in MAIN, f"main.py tak membaca field {f}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("OK semua kontrak protokol sinkron")
