# 语音 AI 助手 — iflyVoice

一款融合语音识别、AI 对话和显示器硬件控制的本地 AI 助手。支持中文语音直说、多种 AI 模型（本地 Ollama / 火山引擎豆包），以及通过 ADB + DDC/CI 协议直接调节显示器亮度、对比度、电源等参数。

---

## 功能概览

### 语音识别（双引擎）
- **浏览器内置 API**：无需配置，直接使用，适合快速体验
- **讯飞语音识别 API**：中文识别准确率更高，支持长语音流式识别（需配置 API 密钥）

### AI 对话（双模型源）
- **本地模型（Ollama）**：qwen3:4b、deepseek-r1:7b 等，本地运行完全免费
- **云端模型（火山引擎豆包）**：doubao-1.5-pro-32k 等，API key 由用户自行提供

> 切换模型来源：页面右上角 **本地(Ollama) / 云端(火山引擎)** 下拉框

### 显示器硬件控制（语音 + 界面）
- 通过 ADB 连接显示器，控制亮度、对比度、输入源、电源模式
- 支持自然语言指令："亮度调成 50%"、"亮度调高一点"、"亮度调到最低"等
- 也可直接拖动右侧面板的滑块操作

---

## 项目结构

```
iflyVoice/
├── index.html          # 主页面
├── main.js             # 应用核心逻辑（语音、AI 对话、I2C 控制调度）
├── style.css           # 样式文件（深灰主题）
├── server.py           # Python 代理服务器（多线程，支持 Ollama/火山引擎代理）
├── ollama-api.js       # Ollama 本地模型客户端（SSE 流式）
├── cloud-api.js        # 火山引擎云端模型客户端（OpenAI 兼容 SSE 流式）
├── iflytek-api.js     # 讯飞语音识别 API 客户端（WebSocket 流式识别）
├── i2c-api.js          # DDC/CI I2C 控制模块（ADB + i2cset）
├── IFLYTEK_SETUP.md    # 讯飞 API 配置说明
├── start-server.bat    # Windows 一键启动脚本
└── README.md           # 本文档
```

---

## 快速开始

### 1. 启动服务器

```bash
cd iflyVoice
python server.py
```

或双击运行 `start-server.bat`。

服务器启动后访问：**http://localhost:18766**

### 2. 配置讯飞语音（可选）

如果使用讯飞语音识别，打开 `iflytek-api.js`，填写从 [讯飞开放平台](https://www.xfyun.cn/) 获取的 APPID、APIKey、APISecret。

### 3. 配置火山引擎云端模型（可选）

在 `server.py` 中修改 `VOLCENGINE_CONFIG` 字典，填入你自己的 API Key 和模型名称：

```python
VOLCENGINE_CONFIG = {
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "YOUR_API_KEY",
    "default_model": "你的模型名称",
}
```

### 4. 连接 ADB 设备（控制显示器，可选）

确保 `adb` 命令在系统 PATH 中，且有显示器通过 USB-C/HDMI 连接并开启 DDC/CI。

---

## 使用方法

1. **语音输入**：点击左侧「开始录音」按钮，对着麦克风说话，识别结果实时显示
2. **发送给 AI**：点击「发送给 AI」或直接在右侧输入框打字
3. **切换模型**：右上角选择「本地(Ollama)」或「云端(火山引擎)」，然后选具体模型
4. **控制显示器**：直接说"亮度调成 60%"等指令，AI 会自动解析并执行 DDC/CI 命令

---

## 技术架构

### 前端
- **Web Speech API**：浏览器内置语音识别，开箱即用
- **讯飞 WebSocket API**：长语音流式识别，需要用户配置密钥
- **SSE（Server-Sent Events）**：Ollama 和火山引擎均通过 SSE 实现流式输出
- **I2C/DDC/CI**：通过 ADB shell 执行 i2cset 命令控制显示器

### 后端（server.py）
- **多线程 HTTPServer**：每个请求独立线程，互不阻塞
- **Ollama 代理**（`/ollama/*`）：原始 Socket 转发，支持 SSE 流式
- **火山引擎代理**（`/cloud/*`）：OpenAI 兼容格式，分块转发 SSE 流
- **I2C 代理**（`/i2c/*`）：执行 adb shell i2cset 命令

### 语音命令解析（i2c-api.js）
支持的自然语言模式：
- 设置值：`亮度调成 50%` / `对比度设为 80`
- 极端值：`亮度调到最低` → 0%，`亮度调到最高` → 100%
- 相对调整：`亮度调高一点` / `对比度调低 5`
- 电源控制：`显示器待机` / `关闭显示器`

---

## 浏览器兼容性

| 浏览器 | 语音识别 | AI 对话 | I2C 控制 |
|--------|---------|---------|---------|
| Chrome / Edge | ✅ 推荐 | ✅ | ✅ |
| Safari | ✅ | ✅ | ✅ |
| Firefox | ❌ 不支持 Web Speech API | ✅ | ✅ |

---

## 常见问题

**Q: 切换到火山引擎后报 404？**
> 需要重启 server.py 以加载最新的代理逻辑。

**Q: 语音控制显示器不生效？**
> 确认 adb devices 能看到设备，且显示器 OSD 中 DDC/CI 已开启。

**Q: 讯飞 API 识别失败？**
> 检查 APPID、APIKey、APISecret 是否填写正确，密钥是否已开通语音听写服务。

---

## 开发备注

- 服务器默认端口：**18766**
- Ollama 默认地址：**127.0.0.1:11434**
- 火山引擎 API 地址：**ark.cn-beijing.volces.com/api/v3**
