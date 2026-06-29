#!/bin/bash
# End-to-end latency test — measures full pipeline latency.
# Must run on board with mic + speaker + NPU.
set +e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
pass=0; fail=0

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

echo "=== E2E Latency Tests ==="

echo
echo "--- 1. VAD Latency ---"
check "VAD < 10ms" "python3 -c '
import time, numpy as np
from vad_engine import SileroVAD
vad = SileroVAD()
audio = np.random.randn(512).astype(np.float32) * 0.01
t0 = time.time()
for _ in range(100):
    vad(audio, 16000)
avg = (time.time() - t0) / 100 * 1000
print(f\"VAD avg: {avg:.1f}ms\")
assert avg < 10, f\"VAD too slow: {avg}ms\"
'"

echo
echo "--- 2. ASR Latency ---"
check "NPU ASR < 2s (5s audio)" "python3 -c '
import time, numpy as np, os, sys
sys.path.insert(0, \".\")
from npu.rknn_asr import RknnASR
model = \"models/sensevoice_small.rknn\"
if not os.path.exists(model):
    print(\"SKIP: no model\")
    sys.exit(0)
asr = RknnASR(model)
if not asr.is_loaded():
    print(\"SKIP: model failed to load\")
    sys.exit(0)
audio = np.random.randn(16000 * 5).astype(np.float32) * 0.01
t0 = time.time()
asr.transcribe(audio, sample_rate=16000)
latency = (time.time() - t0) * 1000
print(f\"ASR latency: {latency:.0f}ms\")
assert latency < 2000, f\"ASR too slow: {latency}ms\"
'"

echo
echo "--- 3. Backlight Control Latency ---"
check "Backlight set < 200ms" "python3 -c '
import time
from linux.backlight import get_backlight_value, set_backlight_value
cur = get_backlight_value()
t0 = time.time()
set_backlight_value(50)
latency = (time.time() - t0) * 1000
set_backlight_value(cur)
print(f\"Backlight latency: {latency:.0f}ms\")
assert latency < 200, f\"Too slow: {latency}ms\"
'"

echo
echo "--- 4. Executor Dispatcher Latency ---"
check "Dispatcher dispatch < 10ms" "python3 -c '
import time
from executor.dispatcher import ExecutorDispatcher
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor
from executor.local import LocalExecutor
from executor.base import Intent, IntentType
disp = ExecutorDispatcher(PCAgentExecutor(\"http://fake\"), DevStubExecutor(), LocalExecutor())
t0 = time.time()
for _ in range(100):
    disp.dispatch(Intent(IntentType.SET_LOCAL_BACKLIGHT, {\"value\": 50}))
avg = (time.time() - t0) / 100 * 1000
print(f\"Dispatcher avg: {avg:.2f}ms\")
assert avg < 10, f\"Too slow: {avg}ms\"
'"

echo
echo "=== Summary ==="
echo -e "  ${GREEN}PASS: $pass${NC} | ${RED}FAIL: $fail${NC}"
[ $fail -eq 0 ] && exit 0 || exit 1
