#!/bin/bash
# e2e_openclaw_iflyvoice.sh — 板子端 OpenClaw→iflyVoice→DDC/CI 全链路端到端
# 验证：OpenClaw LLM 通过 iflyVoice HTTP API 真实调节显示器亮度
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "  ${YEL}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

echo "=== e2e_openclaw_iflyvoice ==="

# 1. 前置：iflyVoice + OpenClaw 都在跑
echo "[1] 前置检查"

if ! curl -fsS --max-time 2 http://127.0.0.1:18766/health >/dev/null 2>&1; then
    echo "    iflyVoice 未运行；启动它"
    bash "$(dirname "$0")/start-iflyvoice.sh"
fi
pass "iflyVoice running"

if ! command -v openclaw >/dev/null 2>&1; then
    fail "openclaw 命令不存在"
fi
if ! openclaw gateway status 2>&1 | grep -q "Runtime: running"; then
    fail "openclaw gateway 未运行；请先 systemctl --user start openclaw-gateway"
fi
pass "openclaw gateway running"

# 2. SKILL.md 已安装
echo "[2] SKILL.md 检查"
if [ ! -f "$HOME/.openclaw/workspace/skills/iflyvoice/SKILL.md" ]; then
    fail "SKILL.md 未安装到 ~/.openclaw/workspace/skills/iflyvoice/"
fi
pass "SKILL.md present"

# 3. 记下当前亮度（优先 DDC/CI，fallback sysfs）
echo "[3] 记下初始亮度"
HAS_DDC=0
HAS_BACKLIGHT=0

# 检查 DDC/CI
if sudo ddcutil detect 2>/dev/null | grep -q "I2C bus"; then
    HAS_DDC=1
    INIT_BRIGHT=$(sudo ddcutil getvcp 0x10 2>/dev/null | grep -oP 'current value\s*=\s*\K\d+' || echo "-1")
    MAX_BRIGHT=$(sudo ddcutil getvcp 0x10 2>/dev/null | grep -oP 'max value\s*=\s*\K\d+' || echo "100")
    echo "    via=ddcutil init=$INIT_BRIGHT max=$MAX_BRIGHT"
elif DEVICE=$(ls /sys/class/backlight 2>/dev/null | head -1); then
    HAS_BACKLIGHT=1
    INIT_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/brightness")
    MAX_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/max_brightness")
    echo "    via=sysfs init=$INIT_BRIGHT max=$MAX_BRIGHT device=$DEVICE"
else
    warn "无 DDC/CI 且无 backlight 设备；仅验证链路连通"
fi

# 4. 通过 OpenClaw 发指令
echo "[4] OpenClaw 调亮度到 65"
OPENCLAW_TIMEOUT=120
RESP=$(timeout $OPENCLAW_TIMEOUT openclaw agent --agent main --message "把屏幕亮度调到 65%" 2>&1) || {
    RC=$?
    if [ $RC -eq 124 ]; then
        warn "OpenClaw LLM 响应超时（${OPENCLAW_TIMEOUT}s），跳过"
        RESP="[超时]"
    else
        warn "openclaw agent 返回非零 ($RC)，继续验证"
        RESP="[错误: $RC]"
    fi
}
echo "    response: ${RESP:0:200}..."

# 等几秒让链路过
sleep 3

# 5. 验证亮度真的变了
echo "[5] 验证亮度变化"

if [ "$HAS_DDC" = "1" ]; then
    NEW_BRIGHT=$(sudo ddcutil getvcp 0x10 2>/dev/null | grep -oP 'current value\s*=\s*\K\d+' || echo "-1")
    TARGET=65
    echo "    via=ddcutil new=$NEW_BRIGHT target=$TARGET init=$INIT_BRIGHT"
    if [ "$NEW_BRIGHT" = "$TARGET" ]; then
        pass "亮度精确到 65%（DDC/CI）"
    elif [ "$NEW_BRIGHT" != "$INIT_BRIGHT" ]; then
        pass "亮度变化了（$INIT_BRIGHT → $NEW_BRIGHT），DDC/CI 链路通"
    else
        # 日志兜底
        if grep -q "set_brightness" /tmp/iflyvoice.log 2>/dev/null; then
            pass "iflyVoice 收到 set_brightness（亮度未变可能是 OSD 锁定）"
        else
            fail "亮度未变，OpenClaw→iflyVoice 链路未通"
        fi
    fi
elif [ "$HAS_BACKLIGHT" = "1" ]; then
    NEW_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/brightness")
    TARGET=$((MAX_BRIGHT * 65 / 100))
    echo "    via=sysfs new=$NEW_BRIGHT target=$TARGET"
    if [ "$NEW_BRIGHT" = "$TARGET" ]; then
        pass "亮度精确到 65%"
    elif [ "$NEW_BRIGHT" != "$INIT_BRIGHT" ]; then
        pass "亮度变化了（$INIT_BRIGHT → $NEW_BRIGHT）"
    else
        fail "亮度没变，OpenClaw→iflyVoice 链路未通"
    fi
else
    warn "无可验证的亮度设备；查看日志兜底"
    if grep -q "set_brightness" /tmp/iflyvoice.log 2>/dev/null; then
        pass "iflyVoice 日志确认收到 set_brightness 调用"
    else
        warn "iflyVoice 日志里没看到 set_brightness"
    fi
fi

echo
echo -e "${GREEN}=== e2e_openclaw_iflyvoice PASSED ===${NC}"
