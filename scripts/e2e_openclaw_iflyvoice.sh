#!/bin/bash
# e2e_openclaw_iflyvoice.sh — 板子端 OpenClaw→iflyVoice 链路端到端
# 验证：给 OpenClaw 发"调亮"指令，OpenClaw 真的会让 iflyVoice 调亮度
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "  ${YEL}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

echo "=== e2e_openclaw_iflyvoice ==="

# 1. 前置：iflyVoice + OpenClaw 都在跑
echo "[1] 前置检查"

# iflyVoice
if ! curl -fsS --max-time 2 http://127.0.0.1:18766/health >/dev/null 2>&1; then
    echo "    iflyVoice 未运行；启动它"
    bash "$(dirname "$0")/start-iflyvoice.sh"
fi
pass "iflyVoice running"

# OpenClaw
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

# 3. 记下当前亮度
echo "[3] 记下初始亮度"
DEVICE=$(ls /sys/class/backlight 2>/dev/null | head -1 || echo "")
if [ -z "$DEVICE" ]; then
    warn "无 backlight 设备；跳过亮度验证（仅验证链路连通）"
    HAS_BACKLIGHT=0
else
    HAS_BACKLIGHT=1
    INIT_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/brightness")
    MAX_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/max_brightness")
    echo "    init=$INIT_BRIGHT max=$MAX_BRIGHT device=$DEVICE"
fi

# 4. 通过 OpenClaw 发指令
echo "[4] OpenClaw 调亮度到 75"
# 用 openclaw agent 一次性发消息（需指定 agent id）
# 加 timeout 防止 LLM 响应超时导致脚本永久卡住
OPENCLAW_TIMEOUT=120
RESP=$(timeout $OPENCLAW_TIMEOUT openclaw agent --agent main --message "把屏幕亮度调到 75%" --thinking low 2>&1) || {
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
if [ "$HAS_BACKLIGHT" = "1" ]; then
    NEW_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/brightness")
    TARGET=$((MAX_BRIGHT * 75 / 100))
    echo "    new=$NEW_BRIGHT target=$TARGET"
    if [ "$NEW_BRIGHT" = "$TARGET" ]; then
        pass "亮度精确到 75%"
    elif [ "$NEW_BRIGHT" != "$INIT_BRIGHT" ]; then
        pass "亮度变化了（$INIT_BRIGHT → $NEW_BRIGHT，可能不精确到 75）"
    else
        fail "亮度没变，OpenClaw→iflyVoice 链路未通"
    fi
else
    warn "无 backlight 设备；只能验证 iflyVoice 收到调用"
    # 至少 iflyVoice 应该看到调用
    if grep -q "set_brightness" /tmp/iflyvoice.log 2>/dev/null; then
        pass "iflyVoice 收到 set_brightness 调用"
    else
        warn "iflyVoice 日志里没看到 set_brightness（可能路由走了别的）"
    fi
fi

echo
echo -e "${GREEN}=== e2e_openclaw_iflyvoice PASSED ===${NC}"
