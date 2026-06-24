# 2026-06-23 Daily Report — DDC/CI 真实硬件控制 + STT 语音识别 + 语音助手 + MCP 集成

## 今日目标

在 OpenClaw Phase 1 基础上，实现：
1. 真实显示器硬件控制（DDC/CI 替代无用的 backlight 路径）
2. 语音转文字（SenseVoiceSmall 替代 DeepSeek 内置 STT）
3. 实时语音对话 + 唤醒词唤醒
4. MCP 工具集成（替代 exec+curl 手工调用）

## 完成情况

### 1. DDC/CI 显示器硬件控制

**新建 `linux/ddcci.py`**：封装 ddcutil CLI，支持 VESA MCCS 标准 VCP 码。
- VCP 0x10 亮度 / 0x12 对比度 / 0x60 输入源 / 0xD6 电源
- 显示器 AOC Q27G10ZE 通过 DisplayPort 连接，I2C bus /dev/i2c-11
- 所有操作通过 sudo ddcutil 执行

**验证结果**：
| 功能 | 测试 | 结果 |
|------|------|------|
| 亮度 | 70→65→100→10→80 (DDC/CI 精确) | ✅ |
| 对比度 | 80→100→10→60 | ✅ |
| 输入源 | DP-1↔HDMI-1 双向切换 | ✅ |
| e2e | OpenClaw LLM 调亮度 65% | ✅ 精确 |

**更新 `executor/local.py`**：DDC/CI 优先，backlight/xrandr 兜底；对比度/输入源从假实现变为真硬件。

### 2. WebDDCUtil VCP 码表查询

**新建 `/api/v1/tools/list_vcp_codes`**：查询 http://192.168.1.213:5002 的 VESA v2.2a VCP 条目（184 条，5 分类）。
- 支持 code hex 过滤和 keyword 搜索
- OpenClaw LLM 成功查询并整理为分类表格

### 3. STT 语音识别

**新建 `/sensevoice/transcribe` 端点**：multipart/form-data 音频 → xinference SenseVoiceSmall → 文本。
- xinference 地址：http://192.168.1.32:9997（已有 sensevoice 模型）
- 管道验证：Client → iflyVoice :18766 → xinference :9997 → text ✅

**新建 `scripts/voice_input.sh`**：ALSA 录音 → STT → OpenClaw 单次语音输入管道。

**OpenClaw STT Provider 方案受阻**：OpenClaw v2026.6.6 阻止 HTTP provider（只允许 HTTPS），改用预处理方案。

### 4. 实时语音助手 + 唤醒词

**新建 `voice_assistant.py`**（~500 行，headless，无 Qt 依赖）：
- 状态机：IDLE → WAKE_LISTEN → COMMAND_LISTEN → PROCESSING → SPEAKING
- 麦克风：sounddevice (ALSA hw:0,0)，16kHz mono
- VAD：Silero VAD (silero_vad.onnx) — 每个 chunk 1-5ms
- 唤醒词："小助手"（可配置，ASR 模糊匹配）
- 命令识别：SenseVoiceSmall via iflyVoice STT
- LLM：OpenClaw agent CLI
- TTS：已禁用（板子无喇叭输出）

**修复过程**：
1. 缓冲拷贝 bug：STT 清空缓冲导致后续检查失败 → deepcopy 快照
2. 主循环阻塞：STT 调用阻塞音频采集 → 后台线程
3. 静音超时过早：STT 在途时超时复位 → pending_wake_checks 计数器
4. 时间戳泄漏：_last_wake_check 跨周期残留 → 每次进入清零
5. TTS 反馈循环：ffplay 音频被 mic 回收 → 非监听状态丢弃音频块
6. OpenClaw 弹窗：改用 --json + 清 DISPLAY 环境变量

**验证结果**：
- 唤醒："小助手" → STT 返回"助手开音量" → 模糊匹配 → 命令"开音量" → OpenClaw 调音量 ✅
- 全链路延迟：VAD(即时) + STT(0.1s) + LLM(~10s)

### 5. MCP 工具集成

**新建 `mcp_server.py`**：Python MCP server (stdio JSON-RPC)，暴露 13 个 iflyVoice 工具。
- 注册方式：`openclaw mcp add iflyvoice --command ...`
- 工具列表：set_brightness, set_contrast, set_volume, set_input, list_inputs, list_apps, launch_app, close_app, focus_app, adjust_brightness, adjust_volume, stt_transcribe, list_vcp_codes
- Probe 确认：13 tools ✅

**替换 exec+curl**：SKILL.md 更新为优先使用 MCP 工具 `iflyvoice__*`。
- 亮度 20→80：LLM 直接调用 ✅
- 输入源 DP→HDMI→DP：LLM 直接切换 ✅

## 今日提交（11 个 commit）

```
eef822c feat(mcp): add MCP server exposing iflyVoice tools to OpenClaw
06dba3a fix(voice): fix wake word detection — reset + async + audio drain
0d69610 fix(voice): fix wake word detection — buffer copy + async STT
3f65837 feat(voice): add real-time voice assistant with wake word
34e1d97 feat(stt): add voice_input.sh
87cb53a feat(stt): add /v1/chat/completions wrapper
e8d9403 feat(stt): add /sensevoice/transcribe endpoint
2d31bb6 fix(ddcci): fix list_input_sources to parse capabilities
19d69e9 feat(vcp): add list_vcp_codes endpoint
f61445e feat(ddcci): add DDC/CI real monitor brightness/contrast control
390459b fix(e2e): add 120s timeout to openclaw agent call
```

## 能力矩阵

```
OpenClaw (DeepSeek v4-pro, :18789)
  ├── MCP Tools (iflyvoice__*)  ← 新增
  ├── exec+curl (SKILL.md, 备用)
  ↓
iflyVoice (Python, :18766)
  ├── /api/v1/tools/* (DDC/CI, 音量, 应用)
  ├── /sensevoice/transcribe (STT)
  ├── /v1/models, /v1/chat/completions (包装器)
  ↓
├── linux/ddcci.py → sudo ddcutil → 显示器 (AOC Q27G10ZE)
├── linux/audio_io.py → pulsectl → PulseAudio
├── app_manager_linux.py → wmctrl/xdotool
├── xinference (192.168.1.32:9997) → SenseVoiceSmall
└── WebDDCUtil (192.168.1.213:5002) → VCP 参考库

voice_assistant.py (常驻, headless)
  sounddevice → Silero VAD → 唤醒词"小助手" → STT → OpenClaw
```

## 待办

1. **推送分支**：`git push origin rk3576_lubancat`（68+ commits）
2. **外接麦克风**：板子自带 mic 灵敏度低，唤醒词首字常丢失
3. **TTS 恢复**：板子喇叭无声，需排查音频输出
4. **list_apps 过滤优化**
5. Phase 2：OpenClaw Node 插件（MCP 已可用，优先级降低）
6. Phase 3：MCP server 化（已提前实现）
