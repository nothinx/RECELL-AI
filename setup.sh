#!/bin/bash
echo "============================================="
echo " RECELL-AI 1-CLICK DEPLOYMENT SCRIPT"
echo "============================================="

# 1. Update system & install dependencies
echo "[*] Installing system dependencies..."
sudo apt update
sudo apt install -y python3.10-venv python3-pip libqt5gui5

# 2. Create Virtual Environment
echo "[*] Creating Python Virtual Environment..."
python3 -m venv venv
source venv/bin/activate

# 3. Install Python requirements
echo "[*] Installing Python libraries (This may take a while)..."
pip install --upgrade pip
pip install -r jetson/requirements.txt

# 4. Create necessary folder structures
echo "[*] Creating data directories..."
mkdir -p jetson/data/passports
mkdir -p jetson/datasets/electrical/nasa/raw
mkdir -p jetson/datasets/vision
mkdir -p jetson/models/weights
mkdir -p jetson/models/engines

echo "============================================="
echo " SETUP COMPLETE!"
echo " To run the application:"
echo " 1. source venv/bin/activate"
echo " 2. cd jetson/src"
echo " 3. python3 ui_dashboard.py"
echo "============================================="
