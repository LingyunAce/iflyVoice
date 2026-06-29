#!/bin/bash
# start-voice-assistant.sh — 启动/停止语音助手常驻服务
# Usage: bash scripts/start-voice-assistant.sh [start|stop|status]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/voice_assistant.pid"
LOG_FILE="/tmp/voice_assistant.log"
VA_SCRIPT="$SCRIPT_DIR/../voice_assistant.py"

action="${1:-start}"

case "$action" in
    start)
        # Check already running
        if [ -f "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                echo "[voice-va] already running (pid=$pid)"
                exit 0
            fi
        fi
        echo "[voice-va] starting..."
        cd "$SCRIPT_DIR/.."
        nohup python3 "$VA_SCRIPT" --daemon >> "$LOG_FILE" 2>&1 &
        sleep 2
        if [ -f "$PID_FILE" ]; then
            echo "[voice-va] started OK (pid=$(cat "$PID_FILE"), log=$LOG_FILE)"
        else
            echo "[voice-va] start failed — check $LOG_FILE"
            exit 1
        fi
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE")
            kill "$pid" 2>/dev/null && echo "[voice-va] stopped (pid=$pid)"
            rm -f "$PID_FILE"
        else
            echo "[voice-va] not running"
        fi
        ;;
    status)
        if [ -f "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                echo "[voice-va] running (pid=$pid)"
            else
                echo "[voice-va] dead (stale pid=$pid)"
                rm -f "$PID_FILE"
            fi
        else
            echo "[voice-va] not running"
        fi
        ;;
    *)
        echo "Usage: $0 [start|stop|status]"
        exit 1
        ;;
esac
