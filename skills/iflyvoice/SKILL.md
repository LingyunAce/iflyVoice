---
name: iflyvoice
description: "控制 RK3576 板子的显示器亮度、系统音量、桌面应用。HTTP API 在 http://127.0.0.1:18766/api/v1/tools/。使用前确认 iflyVoice 服务在运行（curl http://127.0.0.1:18766/health）。"
---

# iflyVoice 硬件控制

iflyVoice 在 127.0.0.1:18766 提供 HTTP API，控制 RK3576 板子的本地硬件。

## 前置条件

- iflyVoice 服务在运行：`bash ~/.openclaw/workspace/skills/iflyvoice/start-iflyvoice.sh`
- 健康检查：`curl -fsS http://127.0.0.1:18766/health`（应返回 `{"ok": true}`）
- 服务挂了 → 提示用户运行 `start-iflyvoice.sh`，**不要重试无限循环**

## 可用能力

| 能力 | 工具 | 说明 |
|------|------|------|
| 亮度 | `set_brightness` | 设为 0-100 的绝对值（DDC/CI 真硬件） |
| 亮度 | `adjust_brightness` | 增量调整（正/负） |
| 对比度 | `set_contrast` | 设为 0-100 的绝对值（DDC/CI） |
| 对比度 | `adjust_contrast` | 增量调整（正/负） |
| 音量 | `set_volume` | 设为 0-100 的绝对值 |
| 音量 | `adjust_volume` | 增量调整（正/负） |
| 应用 | `launch_app` | 启动应用（按名字） |
| 应用 | `close_app` | 关闭应用 |
| 应用 | `focus_app` | 切换/聚焦已运行应用 |
| 应用 | `list_apps` | 列出当前运行的 GUI 进程 |
| 显示器 | `list_monitors` | 列出已连接的输出 + DDC/CI 输入源 |
| 输入源 | `set_input` | 切换显示器输入源（DDC/CI） |
| 语音识别 | `stt` | 语音转文字（SenseVoiceSmall，中文优先） |
| 语音助手 | `voice_start` | 启动实时语音助手（唤醒词"小爱同学"） |
| 语音助手 | `voice_stop` | 停止语音助手 |

## 调用方式

使用 `exec` 工具调 curl。**必须保留完整引号**：

```bash
# 亮度调到 60
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/set_brightness \
  -H "Content-Type: application/json" \
  -d '{"value":60}'

# 亮度 +10（增量）
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/adjust_brightness \
  -H "Content-Type: application/json" \
  -d '{"delta":10}'

# 音量调到 30
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/set_volume \
  -H "Content-Type: application/json" \
  -d '{"value":30}'

# 音量 +20
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/adjust_volume \
  -H "Content-Type: application/json" \
  -d '{"delta":20}'

# 打开 firefox
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/launch_app \
  -H "Content-Type: application/json" \
  -d '{"name":"firefox"}'

# 关闭 firefox
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/close_app \
  -H "Content-Type: application/json" \
  -d '{"name":"firefox"}'

# 切换到 firefox
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/focus_app \
  -H "Content-Type: application/json" \
  -d '{"name":"firefox"}'

# 对比度调到 80
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/set_contrast \
  -H "Content-Type: application/json" \
  -d '{"value":80}'

# 对比度 +10
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/adjust_contrast \
  -H "Content-Type: application/json" \
  -d '{"delta":10}'

# 切换输入源到 HDMI-1
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/set_input \
  -H "Content-Type: application/json" \
  -d '{"code":"11"}'

# 列出已运行应用
curl -fsS http://127.0.0.1:18766/api/v1/tools/list_apps

# 语音转文字（发送音频文件，SenseVoiceSmall 识别）
curl -fsS -X POST http://127.0.0.1:18766/sensevoice/transcribe \
  -F 'file=@/tmp/recording.webm'
# 返回: {"success": true, "text": "识别出的中文文字"}

# 列出已连接显示器 + DDC/CI 输入源
curl -fsS http://127.0.0.1:18766/api/v1/tools/list_monitors
```

## 失败处理

返回 `ok: false` 时：
- `err` 字段是人类可读错误，**用自然语言告诉用户**
- `code` 字段是错误码（ERR_LOCAL_BACKLIGHT / ERR_LOCAL_AUDIO / ERR_APP_NOT_FOUND / ERR_APP_NOT_RUNNING / ERR_NO_WINDOW_MANAGER / ERR_UNSUPPORTED / ERR_BAD_REQUEST）
- 7（curl 退出码）= 服务未起 → 提示运行 `start-iflyvoice.sh`

## 能力边界

**能做**：
- 调亮度/对比度（DDC/CI 真实硬件控制，通过 ddcutil）
- 切换显示器信号输入源（DisplayPort/HDMI 切换，DDC/CI VCP 0x60）
- 调音量（依赖 PulseAudio/PipeWire 运行）
- 启动/关闭/切换大部分桌面应用（firefox、chromium、gnome-terminal、code 等）

**不能做**：
- B 站视频搜索（本期不支持，ERR_UNSUPPORTED）
- 关闭/重启系统
- 任何破坏性操作（rm -rf、kill 关键进程等）

## 中文指令示例

| 用户说 | 你应执行 |
|--------|---------|
| 把屏幕调亮一点 | `adjust_brightness` `{"delta":10}` |
| 把屏幕调暗一点 | `adjust_brightness` `{"delta":-10}` |
| 亮度调到 50 | `set_brightness` `{"value":50}` |
| 太刺眼了 | `adjust_brightness` `{"delta":-15}` |
| 声音大点 | `adjust_volume` `{"delta":15}` |
| 音量调到 80 | `set_volume` `{"value":80}` |
| 打开浏览器 | `launch_app` `{"name":"firefox"}` |
| 关闭 firefox | `close_app` `{"name":"firefox"}` |
| 切到终端 | `focus_app` `{"name":"terminal"}` |
| 切换到 DP | `set_input` `{"code":"0f"}` |
| 切换到 HDMI | `set_input` `{"code":"11"}` |
| 现在跑着什么应用 | `list_apps` |

## 注意事项

- **重要：DDC/CI 显示器控制始终可用**。`list_monitors` 返回两个字段：
  `xrandr_outputs`（可能为空，取决于桌面会话）和 `ddc_sources`（DDC/CI 真实探测）。
  即使 `xrandr_outputs` 为空，DDC/CI 路径依然有效。不要因为 xrandr 返回空就认为无显示器。
- **set_input 直接执行**：不需要先检查"是否支持"——直接调 `set_input`，根据返回结果判断。
- 用户说"亮一点"而当前是 90 → 调到 100，不要超过
- 用户说"打开 XX"但找不到 XX → 提示当前可用的应用
- 每次硬件操作后**用 1-2 句自然语言回复用户**，不要说"已发送 curl 请求"
- 操作失败时给出**具体原因**（不只是"操作失败"）
