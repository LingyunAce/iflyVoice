#!/bin/bash
# 启动 widget 前预检环境；不通过则非零退出。
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
fail=0

check_pass() { echo -e "  ${GREEN}[OK]${NC}  $1"; }
check_warn() { echo -e "  ${YEL}[WARN]${NC} $1"; }
check_fail() { echo -e "  ${RED}[FAIL]${NC} $1"; fail=1; }

echo "=== ARM64 环境预检 ==="

# 1. 架构
echo "[1] 架构"
if [ "$(uname -m)" = "aarch64" ]; then
    check_pass "aarch64"
else
    check_warn "当前 $(uname -m)，非 aarch64（NPU 相关项会跳过）"
fi

# 2. Python 依赖
echo "[2] Python 依赖"
for pkg in PySide6 sounddevice numpy onnxruntime requests edge_tts Pillow; do
    if python3 -c "import ${pkg}" 2>/dev/null; then
        check_pass "$pkg"
    else
        check_fail "$pkg 未安装（pip install $pkg）"
    fi
done

# 3. 系统命令
echo "[3] 系统命令"
for cmd in ffmpeg ffplay pactl xrandr fc-list; do
    if command -v $cmd >/dev/null 2>&1; then
        check_pass "$cmd"
    else
        check_warn "$cmd 缺失（部分功能不可用）"
    fi
done

# 4. 设备权限
echo "[4] 设备权限"
if [ -d /dev/snd ]; then
    if [ -r /dev/snd ] && [ -w /dev/snd ]; then
        check_pass "/dev/snd 可读写"
    else
        check_fail "/dev/snd 不可读写（sudo usermod -aG audio $USER）"
    fi
else
    check_fail "/dev/snd 不存在"
fi

if [ -d /dev/dri ]; then
    check_pass "/dev/dri 存在（GPU 渲染可用）"
else
    check_warn "/dev/dri 不存在（Qt 走 sw 渲染）"
fi

# 5. 字体
echo "[5] 字体"
if fc-list :lang=zh 2>/dev/null | grep -q .; then
    check_pass "中文字体"
else
    check_fail "未装中文字体（sudo apt install fonts-noto-cjk）"
fi

# 6. NPU（仅 aarch64 检查）
if [ "$(uname -m)" = "aarch64" ]; then
    echo "[6] NPU"
    if [ -e /dev/rknpu ]; then
        check_pass "/dev/rknpu 存在"
    else
        check_warn "/dev/rknpu 不存在（ASR 将走远端）"
    fi
    if python3 -c "import rknn" 2>/dev/null; then
        check_pass "rknn 库可导入"
    else
        check_warn "rknn 库不可用（ASR 将走远端）"
    fi
    # RKNN model file
    if [ -f models/sensevoice_small.rknn ]; then
        check_pass "sensevoice_small.rknn model file"
    else
        check_warn "sensevoice_small.rknn not found (ASR will use remote)"
    fi
fi

# 7. 网络
echo "[7] 网络"
if curl -s --max-time 3 http://192.168.1.32:11434/api/tags >/dev/null 2>&1; then
    check_pass "Ollama 远端可达"
else
    check_warn "Ollama 远端不可达（AI 对话不可用）"
fi

echo
if [ $fail -eq 0 ]; then
    echo -e "${GREEN}预检通过${NC}"
    exit 0
else
    echo -e "${RED}预检失败，请处理标记为 FAIL 的项${NC}"
    exit 1
fi
