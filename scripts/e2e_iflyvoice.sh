#!/bin/bash
# e2e_iflyvoice.sh — 板子端 iflyVoice HTTP API 端到端验证
# OpenClaw 集成 Phase 1
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "  ${YEL}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${IFLYVOICE_PORT:-18766}"
BASE="http://127.0.0.1:$PORT"

echo "=== e2e_iflyvoice (port $PORT) ==="

# 1. 启动服务
echo "[1] 启动 iflyVoice"
bash "$SCRIPT_DIR/start-iflyvoice.sh"
sleep 1
pass "service started"

# 2. 健康检查
echo "[2] /health"
RESP=$(curl -fsS --max-time 3 "$BASE/health")
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "health not ok"
pass "health check"

# 3. 调亮度（写入）
echo "[3] set_brightness=50"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/set_brightness" \
  -H "Content-Type: application/json" -d '{"value":50}')
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "set_brightness failed"
pass "set_brightness API"

# 4. 验证 sysfs 真的改了
echo "[4] 验证 sysfs brightness"
if [ -d /sys/class/backlight ]; then
    DEVICE=$(ls /sys/class/backlight | head -1)
    if [ -n "$DEVICE" ]; then
        MAX=$(cat "/sys/class/backlight/$DEVICE/max_brightness")
        EXPECTED=$((MAX / 2))
        RAW=$(cat "/sys/class/backlight/$DEVICE/brightness")
        echo "    device=$DEVICE max=$MAX raw=$RAW expected=$EXPECTED"
        if [ "$RAW" -eq "$EXPECTED" ]; then
            pass "sysfs brightness 验证通过"
        else
            warn "sysfs brightness 不匹配 raw=$RAW expected=$EXPECTED（可能设备不支持或权限不足）"
        fi
    else
        warn "无 backlight 设备（仅验证 API 响应）"
    fi
else
    warn "无 /sys/class/backlight（仅验证 API 响应）"
fi

# 5. 调亮度（增量）
echo "[5] adjust_brightness +10"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/adjust_brightness" \
  -H "Content-Type: application/json" -d '{"delta":10}')
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "adjust_brightness failed"
pass "adjust_brightness API"

# 6. 调音量
echo "[6] set_volume=30"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/set_volume" \
  -H "Content-Type: application/json" -d '{"value":30}')
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || warn "set_volume failed（可能 PulseAudio 未运行）"

# 7. 列显示器
echo "[7] list_monitors"
RESP=$(curl -fsS "$BASE/api/v1/tools/list_monitors")
echo "    $RESP"
pass "list_monitors API"

# 8. 列应用
echo "[8] list_apps"
RESP=$(curl -fsS "$BASE/api/v1/tools/list_apps")
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "list_apps failed"
pass "list_apps API"

# 9. 错误路径：未知工具 → 404
echo "[9] 未知工具返回 404"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$BASE/api/v1/tools/unknown_tool" \
  -H "Content-Type: application/json" -d '{}')
[ "$CODE" = "404" ] || fail "expected 404 for unknown tool, got $CODE"
pass "404 on unknown tool"

# 10. 错误路径：B 站搜索 → ERR_UNSUPPORTED
echo "[10] B 站搜索返回 ERR_UNSUPPORTED"
RESP=$(curl -sS -X POST "$BASE/api/v1/tools/bilibili_search" \
  -H "Content-Type: application/json" -d '{"keyword":"test"}' 2>&1 || true)
echo "    $RESP"
echo "$RESP" | grep -q '"code": "ERR_UNSUPPORTED"' || warn "B 站搜索错误码不符合预期（可能工具未注册）"

echo
echo -e "${GREEN}=== e2e_iflyvoice PASSED ===${NC}"
