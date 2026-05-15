# 语音 AI 助手 — iflyVoice

一款融合语音识别、AI 对话和显示器硬件控制的桌面 AI 助手。

---

## 两种模式

### 桌面悬浮球（推荐）

PySide6 桌面应用，支持语音唤醒、实时对话、显示器控制。

**启动方式：**
```bash
# 方式一：批处理启动
start-widget.bat

# 方式二：手动启动
python widget.py
```

**核心功能：**
- 语音唤醒：说"小助手"唤醒，支持 VAD 静音检测
- 文字/语音双输入：点击悬浮球展开聊天面板
- AI 对话：基于 Ollama 本地模型，流式输出 + 流式 TTS 朗读
- 显示器控制：语音调节亮度、对比度、音量
- 三层意图识别：Regex → LLM 语义理解 → 普通对话
- 设置面板：配置音频服务、Ollama 地址、模型选择、麦克风设备

**显示器控制：**

| 控制项 | 支持 DDC/CI | 不支持 DDC/CI |
|--------|------------|---------------|
| 亮度 | 硬件调节（DDC/CI） | 软件调节（WMI） |
| 音量 | 系统原生控制 | 系统原生控制 |
| 对比度 | 硬件调节（DDC/CI） | 不支持，提示用户 |

**语音指令示例：**
- 标准指令："亮度50"、"音量加20"、"静音"
- 语义理解："太刺眼了"、"看不清"、"太吵了"
- 复合指令："亮度和音量都调高一点"

### Web 版本（旧版）

浏览器端应用，支持语音识别、AI 对话、显示器控制面板。

**启动方式：**
```bash
python server.py
# 访问 http://localhost:18766
```

---

## 项目结构

```
iflyVoice/
├── widget.py               # 桌面悬浮球主程序（PySide6）
├── voice_pipeline.py       # 语音管线（VAD、唤醒词、ASR、意图识别、TTS）
├── server.py               # 后端服务（Ollama 代理、显示器控制、ASR 代理）
├── settings.json           # 配置文件（服务地址、模型、麦克风）
├── start-widget.bat        # 桌面版启动脚本
├── start-server.bat        # Web 版启动脚本
├── embedded_static.py      # 打包用静态资源
├── build.py                # PyInstaller 打包脚本
├── VoiceAI.spec            # PyInstaller 配置
├── nircmd.exe              # Windows 命令行工具
├── index.html              # Web 版主页面
├── main.js                 # Web 版核心逻辑
├── style.css               # Web 版样式
├── ollama-api.js           # Ollama 客户端
├── iflytek-api.js          # 讯飞语音识别客户端
├── i2c-api.js              # DDC/CI I2C 控制模块
├── native-display-api.js   # Windows 内置屏幕控制
├── sensevoice-api.js       # SenseVoice ASR 客户端
├── ddcci-api.js            # DDC/CI API 模块
├── IFLYTEK_SETUP.md        # 讯飞 API 配置说明
└── README.md               # 本文档
```

---

## 技术栈

### 桌面悬浮球
- **PySide6**：Qt for Python，桌面 UI 框架
- **Silero VAD**：语音活动检测，判断用户是否在说话
- **SenseVoice**：语音识别（ASR），通过 HTTP API 调用
- **Ollama**：本地大语言模型，用于意图识别和对话
- **edge-tts**：微软 TTS 引擎，流式生成语音
- **sounddevice**：音频采集（麦克风输入）
- **pycaw**：Windows 音量控制

### Web 版本
- **Web Speech API**：浏览器内置语音识别
- **SSE**：Ollama 流式输出
- **I2C/DDC/CI**：通过 ADB 控制显示器

---

## 配置说明

编辑 `settings.json`：

```json
{
  "mic_device": "",                    // 麦克风设备（空=默认）
  "mute_tts": false,                  // 是否禁止自动朗读
  "audio_url": "http://192.168.1.32:9997",   // 音频服务地址（SenseVoice ASR）
  "ollama_url": "http://192.168.1.32:11434", // Ollama 服务地址
  "ollama_model": "qwen3-vl:4b"       // Ollama 模型名称
}
```

也可通过桌面悬浮球的设置界面配置（右键悬浮球 → 设置）。

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
