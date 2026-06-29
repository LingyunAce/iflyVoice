#!/bin/bash
# voice_input.sh — 语音输入管道：录音 → iflyVoice STT (SenseVoiceSmall) → OpenClaw
# 替代 OpenClaw 内置的 DeepSeek STT，解决中文乱码问题
#
# 用法:
#   bash scripts/voice_input.sh              # 默认: 录5秒，发送到 OpenClaw
#   bash scripts/voice_input.sh -d 10        # 录10秒
#   bash scripts/voice_input.sh -f file.wav  # 从已有文件识别
#   bash scripts/voice_input.sh --text-only  # 只返回文本，不发 OpenClaw
#
# 依赖: arecord (alsa-utils), curl, openclaw

set -e

IFLYVOICE_URL="${IFLYVOICE_URL:-http://127.0.0.1:18766}"
AUDIO_FILE="/tmp/iflyvoice_stt.wav"
DURATION=5
FILE_INPUT=""
TEXT_ONLY=false
OPENCLAW_ARGS="--agent main"

usage() {
    echo "Usage: $0 [-d seconds] [-f audio.wav] [--text-only] [--agent name]"
    echo "  默认: ALSA 录音 5 秒 → STT → OpenClaw 发送"
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        -d) DURATION="$2"; shift 2 ;;
        -f) FILE_INPUT="$2"; shift 2 ;;
        --text-only) TEXT_ONLY=true; shift ;;
        --agent) OPENCLAW_ARGS="--agent $2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown: $1"; usage ;;
    esac
done

# ── 1. 获取音频 ──
if [ -n "$FILE_INPUT" ]; then
    AUDIO_FILE="$FILE_INPUT"
    echo "[voice] 使用文件: $AUDIO_FILE"
else
    echo "[voice] 录音 ${DURATION}s (16kHz mono)... 请说话"
    arecord -D hw:0,0 -d "$DURATION" -f S16_LE -r 16000 -c 1 "$AUDIO_FILE" 2>/dev/null
    echo "[voice] 录音完成 ($(du -h "$AUDIO_FILE" | cut -f1))"
fi

# ── 2. STT 识别 ──
echo "[voice] 识别中..."
STT_RESULT=$(curl -fsS --max-time 30 -X POST "$IFLYVOICE_URL/sensevoice/transcribe" \
    -F "file=@$AUDIO_FILE" 2>&1) || {
    echo "[voice] STT 失败: $STT_RESULT"
    exit 1
}

# Extract text from JSON response
TEXT=$(echo "$STT_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('text',''))" 2>/dev/null || echo "")

if [ -z "$TEXT" ]; then
    echo "[voice] 未识别到语音内容"
    exit 0
fi

echo "[voice] 识别结果: $TEXT"

# ── 3. 发送到 OpenClaw ──
if $TEXT_ONLY; then
    echo "[voice] --text-only 模式，不发送到 OpenClaw"
    exit 0
fi

echo "[voice] 发送到 OpenClaw..."
openclaw agent $OPENCLAW_ARGS --message "$TEXT" 2>&1

echo "[voice] 完成"
