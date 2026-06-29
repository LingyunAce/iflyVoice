#!/bin/bash
# RK3576 (Ubuntu 22.04 aarch64) 启动脚本
set -e

cd "$(dirname "$0")"

# 预检
if [ -f scripts/check_arm64.sh ]; then
    bash scripts/check_arm64.sh
fi

# 激活 venv
if [ -d .venv ]; then
    source .venv/bin/activate
fi

# 关旧进程
pkill -f "python.*widget.py" 2>/dev/null || true
sleep 0.5

# 启动
exec python widget.py
