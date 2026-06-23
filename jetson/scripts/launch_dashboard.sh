#!/bin/bash
# Launcher untuk recell.service — cari Xauthority GDM secara dinamis
# agar tidak bergantung pada hardcode UID pengguna.

XAUTH=$(ls /run/user/*/gdm/Xauthority 2>/dev/null | head -1)
if [ -z "$XAUTH" ]; then
    XAUTH="$HOME/.Xauthority"
fi

export DISPLAY=:0
export XAUTHORITY="$XAUTH"

# Unbuffered: di bawah systemd stdout adalah pipe → block-buffered, jadi log
# print() (mis. [TX]/[RX]/[1]) nyangkut di buffer & telat masuk journal. -u
# memaksa real-time agar diagnosa via journalctl akurat.
export PYTHONUNBUFFERED=1
cd /home/r2c/RECELL-AI/jetson/src
exec /home/r2c/RECELL-AI/venv/bin/python -u ui_dashboard.py --fullscreen
