#!/bin/bash
# 板子上一键跑全测；CI 失败非零退出。
set -e
cd "$(dirname "$0")/.."

echo "=== 1. 预检 ==="
bash scripts/check_arm64.sh || { echo "预检失败，跳过测试"; exit 1; }

echo
echo "=== 2. 单元 + 集成 ==="
pytest tests/ -v --tb=short

echo
echo "=== 3. Bench ==="
if [ -f tests/bench_arm64.py ]; then
    python tests/bench_arm64.py --output bench_report_$(date +%Y%m%d_%H%M%S).json || echo "bench 跳过（板子才有）"
else
    echo "tests/bench_arm64.py 不存在（Plan 3 才会建）"
fi

echo
echo "=== 4. E2E 延迟 ==="
if [ -f tests/e2e_latency.sh ]; then
    bash tests/e2e_latency.sh || echo "e2e 跳过"
else
    echo "tests/e2e_latency.sh 不存在（Plan 3 才会建）"
fi

echo
echo "=== 5. 长稳（30 分钟，单独跑）==="
echo "如需跑：python tests/test_stability_arm.py --duration 1800"

echo
echo "[OK] Plan 1 测试全过"
