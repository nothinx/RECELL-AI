#!/bin/bash
# Launcher untuk recell.service — cari Xauthority GDM secara dinamis
# agar tidak bergantung pada hardcode UID pengguna.

XAUTH=$(ls /run/user/*/gdm/Xauthority 2>/dev/null | head -1)
if [ -z "$XAUTH" ]; then
    XAUTH="$HOME/.Xauthority"
fi

export DISPLAY=:0
export XAUTHORITY="$XAUTH"

cd /home/r2c/RECELL-AI/jetson/src
exec /home/r2c/RECELL-AI/venv/bin/python ui_dashboard.py --fullscreen
