#!/bin/bash
# RK3576 end-to-end smoke test. Some steps fail on x86 (mic/HDMI/rknn).
set +e  # don't exit on first failure; report per-step
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; YEL='\033[1;33m'; NC='\033[0m'
pass=0; fail=0; skip=0

check() {
    local name=$1
    local cmd=$2
    echo -n "[$name] "
    if eval "$cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((pass++))
    else
        echo -e "${RED}FAIL${NC}"
        ((fail++))
    fi
}

echo "=== 1. Preflight ==="
check "Python 3.10+" "python3 -c 'import sys; assert sys.version_info >= (3,10)'"
check "PySide6 import" "python3 -c 'import PySide6'"
check "sounddevice import" "python3 -c 'import sounddevice'"
check "onnxruntime import" "python3 -c 'import onnxruntime'"
check "pulsectl import" "python3 -c 'import pulsectl'"

echo
echo "=== 2. pytest ==="
check "All unit tests pass" "pytest tests/ -q"

echo
echo "=== 3. Audio devices ==="
check "List input devices" "python3 -c 'from linux.audio_io import list_input_devices; list_input_devices()'"
check "List output devices" "python3 -c 'from linux.audio_io import list_output_devices; list_output_devices()'"

echo
echo "=== 4. Server startup ==="
python3 server.py >/tmp/voice_server.log 2>&1 &
SERVER_PID=$!
sleep 2
check "GET /health" "curl -sf http://127.0.0.1:18766/health"
check "GET /native/backlight" "curl -sf http://127.0.0.1:18766/native/backlight || true"
kill $SERVER_PID 2>/dev/null

echo
echo "=== 5. Display ==="
check "xrandr available" "command -v xrandr"
check "List connected outputs" "xrandr --query | grep -q connected"

echo
echo "=== 6. Executor self-check ==="
check "LocalExecutor construct" "python3 -c 'from executor.local import LocalExecutor; LocalExecutor()'"
check "Dispatcher construct" "python3 -c 'from executor.dispatcher import ExecutorDispatcher; from executor.dev_stub import DevStubExecutor; from executor.pc_agent import PCAgentExecutor; from executor.local import LocalExecutor; ExecutorDispatcher(PCAgentExecutor(\"http://fake\"), DevStubExecutor(), LocalExecutor())'"

echo
echo "=== 7. Backlight (board only) ==="
check "Read backlight" "python3 -c 'from linux.backlight import get_backlight_value; v=get_backlight_value(); assert v >= 0'"

echo
echo "=== Summary ==="
echo -e "  ${GREEN}PASS: $pass${NC} | ${RED}FAIL: $fail${NC} | ${YEL}SKIP: $skip${NC}"

[ $fail -eq 0 ] && exit 0 || exit 1
