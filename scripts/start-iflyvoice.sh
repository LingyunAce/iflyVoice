#!/bin/bash
# 启动 iflyVoice HTTP 服务（绑 loopback, 端口 18766）
# OpenClaw 集成 Phase 1 — 让 OpenClaw 通过 HTTP API 调 iflyVoice
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 默认参数
PORT="${IFLYVOICE_PORT:-18766}"
BIND="${IFLYVOICE_BIND:-127.0.0.1}"
LOG_FILE="${IFLYVOICE_LOG:-/tmp/iflyvoice.log}"
PID_FILE="${IFLYVOICE_PID:-/tmp/iflyvoice.pid}"

# 检查已经在跑
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[iflyvoice] already running (pid $(cat "$PID_FILE"))"
    exit 0
fi

cd "$PROJECT_DIR"

# 启动
echo "[iflyvoice] starting on $BIND:$PORT (log: $LOG_FILE)"
nohup python3 server.py --port "$PORT" --bind "$BIND" \
    > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

# 等 1s 验证启动成功
sleep 1
if ! kill -0 "$PID" 2>/dev/null; then
    echo "[iflyvoice] FAILED to start; check $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

# 健康检查
if curl -fsS --max-time 2 "http://$BIND:$PORT/health" > /dev/null 2>&1; then
    echo "[iflyvoice] started OK (pid $PID, http://$BIND:$PORT)"
else
    echo "[iflyvoice] started (pid $PID) but health check failed; see $LOG_FILE"
    exit 1
fi
