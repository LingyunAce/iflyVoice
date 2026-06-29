#!/bin/bash
# 在 RK3576 (Ubuntu 22.04 aarch64) 上跑：bash install-arm64.sh
set -e

echo "[1/4] 系统依赖"
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv \
    pulseaudio pulseaudio-utils \
    alsa-utils \
    ffmpeg \
    fonts-noto-cjk \
    libxcb-cursor0 libxkbcommon-x11-0 \
    i2c-tools

echo "[2/4] Python 虚拟环境"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

echo "[3/4] Python 依赖"
pip install -r requirements-arm64.txt

echo "[4/4] 完成"
echo "激活 venv: source .venv/bin/activate"
echo "预检环境:  bash scripts/check_arm64.sh"
