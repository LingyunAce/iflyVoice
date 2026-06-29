# 语音 AI 助手 — iflyVoice

融合语音识别、AI 对话、显示器硬件控制和桌面应用管理的桌面 AI 助手。

---

## 两种模式

### 桌面悬浮球（推荐）

PySide6 桌面应用，支持语音唤醒、实时对话、显示器控制、桌面应用管理。

**启动方式：**
```bash
# 方式一：批处理启动（推荐）
start-widget.bat

# 方式二：手动启动
python widget.py
```

**核心功能：**
- 语音唤醒：说"小助手"唤醒，支持 VAD 静音检测
- 文字/语音双输入：点击悬浮球展开聊天面板
- AI 对话：基于 Ollama 本地模型，流式输出 + 流式 TTS 朗读
- 显示器控制：语音调节亮度、对比度、色温、音量、输入源
- 桌面应用控制：打开/关闭/切换应用、查询已安装应用列表
- B 站视频搜索：直接搜索并打开视频
- 设置面板：配置音频服务、Ollama 地址、模型选择、麦克风设备、唤醒词

**显示器控制：**

| 控制项 | 支持 DDC/CI | 不支持 DDC/CI |
|--------|------------|---------------|
| 亮度 | 硬件调节（DDC/CI） | 软件调节（WMI） |
| 音量 | 系统原生控制 | 系统原生控制 |
| 对比度 | 硬件调节（DDC/CI） | 不支持，提示用户 |
| 色温 | 硬件调节（DDC/CI） | 软件调节（Gamma 曲线） |
| 输入源 | DDC/CI 切换 | 不支持，提示用户 |

**语音指令示例：**
- 标准指令："亮度50"、"音量加20"、"切换到HDMI"
- 语义理解："太刺眼了"、"看不清"、"太吵了"
- 复合指令："亮度和音量都调高一点"
- 桌面应用："打开微信"、"关闭 QQ"、"切换到浏览器"
- B 站："B站搜索 Python 教程"

### Web 版本（旧版）

浏览器端应用，通过 `server.py` 启动，访问 `http://localhost:18766`。

**启动方式：**
```bash
start-server.bat
# 或
python server.py
```

> 备注：Web 版的静态资源（`web/static/`）当前未直接被服务（运行时由 `embedded_static.py` 内嵌版本提供）。
> `web/` 目录下的文件作为开发参考和 `embedded_static.py` 的源材料保留。

---

## 项目结构

```
iflyVoice/
├── widget.py               # 桌面悬浮球主程序（PySide6）
├── voice_pipeline.py       # 语音管线（VAD、唤醒词、ASR、意图识别、TTS）
├── server.py               # HTTP 服务（Ollama 代理、显示器控制、ASR 代理）
├── app_manager.py          # 桌面应用管理（扫描、启动、关闭、切换）
├── vad_engine.py           # Silero VAD 引擎
├── utils.py                # 共享工具（日志、Markdown 清理）
├── embedded_static.py      # 打包用嵌入的 Web 静态资源
├── settings.json           # 配置文件
├── silero_vad.onnx         # VAD 模型
├── nircmd.exe              # Windows 音量控制工具
│
├── start-widget.bat        # 桌面版启动脚本
├── start-server.bat        # Web 版启动脚本
│
├── web/                    # Web 版（旧版/开发参考）
│   ├── static/             # 静态资源（HTML / JS / CSS）
│   │   ├── index.html
│   │   ├── main.js
│   │   ├── style.css
│   │   ├── iflytek-api.js
│   │   ├── i2c-api.js
│   │   ├── native-display-api.js
│   │   ├── sensevoice-api.js
│   │   ├── ddcci-api.js
│   │   ├── ollama-api.js
│   │   └── test-iflytek.html
│   └── IFLYTEK_SETUP.md    # 讯飞 API 配置说明
│
├── build/                  # 打包相关
│   ├── build.py            # PyInstaller 打包脚本（使用相对路径）
│   └── VoiceAI.spec        # PyInstaller 配置（使用相对路径）
│
├── .gitignore
└── README.md
```

---

## 技术栈

### 桌面悬浮球
- **PySide6**：Qt for Python，桌面 UI 框架
- **Silero VAD**：语音活动检测（ONNX Runtime 推理）
- **SenseVoice**：语音识别（ASR），通过 HTTP API 调用
- **Ollama**：本地大语言模型，用于意图识别和对话
- **edge-tts**：微软 TTS 引擎，流式生成语音
- **sounddevice**：音频采集（麦克风输入）
- **pycaw**：Windows 音量控制
- **ffmpeg + ffplay**：音频转码与播放
- **PowerShell + WMI**：显示器亮度/对比度软调节
- **DDC/CI (ctypes)**：显示器硬件控制
- **Win32 API**：桌面应用窗口枚举与切换

### Web 版本
- **Web Speech API**：浏览器内置语音识别
- **SSE**：Ollama 流式输出
- **I2C/DDC/CI**：通过 ADB 控制显示器

---

## 配置说明

编辑 `settings.json`：

```json
{
  "mic_device": "",                              // 麦克风设备（空=默认）
  "mute_tts": false,                             // 是否禁止自动朗读
  "wake_word": "小助手",                         // 唤醒词
  "audio_url": "http://192.168.1.32:9997",       // 音频服务地址（SenseVoice ASR）
  "ollama_url": "http://192.168.1.32:11434",     // Ollama 服务地址
  "ollama_model": "qwen3-vl:2b",                 // Ollama 模型名称
  "logo_path": "..."                             // 头像路径（可选）
}
```

也可通过桌面悬浮球的设置界面配置（右键悬浮球 → 设置）。

---

## 打包

```bash
# 方式一：使用 build.py（推荐，自动使用相对路径）
python build/build.py

# 方式二：直接使用 spec
pyinstaller build/VoiceAI.spec
```

输出：`dist/VoiceAI.exe`

---

## 常见问题

**Q: 唤醒词"小助手"没反应？**
> 检查麦克风是否正常工作，确认音频服务地址配置正确。

**Q: LLM 意图识别超时？**
> 超时会自动回退到普通对话，不会报错。检查 Ollama 服务是否可达。

**Q: 对比度无法调节？**
> 不支持 DDC/CI 的显示器无法调节对比度，系统会提示"当前显示器不支持DDC/CI"。

**Q: TTS 没有声音？**
> 检查系统音量是否静音，确认 `mute_tts` 设置为 `false`。

**Q: 打包后的 exe 在其他机器上启动失败？**
> 确保目标机器是 Windows 10/11，且已安装 ffmpeg（ffmpeg.exe + ffplay.exe 在 PATH 中）。

---

## RK3576 鲁班猫移植 (Linux/aarch64)

将本项目作为 Win PC 的语音代理前端运行在 RK3576 鲁班猫（Ubuntu 22.04 aarch64）上。

### 架构

- **RK3576** = 语音前端：mic 采集 + NPU 跑 ASR/唤醒词 + UI + TTS 播放
- **Win PC** = 执行端：显示器 DDC-CI、桌面应用、B 站搜索（通过 `executor/pc_agent.py` 调 HTTP）
- 见 `docs/superpowers/specs/2026-06-17-rk3576-port-design.md` 详细设计

### 一键安装

```bash
bash install-arm64.sh
```

### 启动

```bash
bash start-widget.sh
```

### 预检

```bash
bash scripts/check_arm64.sh
```

### 测试

```bash
bash scripts/run_all_arm64.sh
```

### 限制

- Win PC agent 本期只写了接口契约（`docs/WIN_PC_AGENT_API.md`），实现放下一期
- NPU 跑 ASR 在 Plan 3 实现
- 本期 executor 默认走 `dev_stub`；要连真 PC 改 `settings.json` 的 `winpc_agent_url`

### 实施计划

- Plan 1 (本计划): 架构基座 — executor 抽象 + server /native + Win Agent API 契约
- Plan 2: Linux 用户面移植 — audio_io / widget / voice_pipeline
- Plan 3: NPU 接入 + ARM 验证门禁
