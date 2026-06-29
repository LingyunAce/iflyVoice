# 2026-06-24 Daily Report — 语音识别优化 + USB RNDIS + 文件传输技能 + 新技能安装

## 今日目标

1. 修复语音识别效果差的问题
2. 建立板子↔PC文件传输管道（USB RNDIS + 技能标准化）
3. 扩展 DDC/CI 控制能力（色温、RGB 增益）
4. 安装外部技能到 OpenClaw

## 完成情况

### 1. 语音识别优化

**问题定位**：短音频 + 弱麦克风 = 唤醒词首字丢失。`voice_input.sh`（录 5s 整句）识别完美，`voice_assistant.py`（0.5s 短片段检查）识别失败。

**根因分析**（对比 three paths）：
| 差异 | voice_input.sh | voice_pipeline.py | voice_assistant.py (旧) |
|------|---------------|-------------------|------------------------|
| 录音 | arecord 直通 ALSA | sounddevice (device=None) | sounddevice (device=0) |
| 缓冲 | 固定 5s | deque(maxlen=100) | 无上限 |
| 静音超时 | N/A | 3s wake / 0.7s cmd | 10s wake / 1.5s cmd |
| STT 格式 | WAV | Opus WebM (ffmpeg) | WAV |

**v2 重构**：放弃分段唤醒检查，改为录整句 → 一次 STT → 判断唤醒词。
- 状态机从 5 个状态减为 3 个（IDLE → LISTENING → PROCESSING）
- 代码从 500 行减到 280 行
- 加预缓冲（VAD 触发前 0.5s 音频）防止首字丢失
- 静音超时对齐桌面版（3s / 0.7s）
- deque 设 maxlen=190（~6s）限制缓冲

### 2. DDC/CI 色温 + RGB 增益

**新增功能**：
| 功能 | VCP | API |
|------|-----|-----|
| 色温预设 | 0x14 | `set_color_temp {"preset":"6500 K"}` |
| RGB 增益 | 0x16/18/1A | `set_rgb_gain {"red":50,"green":50,"blue":50}` |

- `linux/ddcci.py`：get/set_color_preset, list_color_presets, set_rgb_gain, get_rgb_gain
- `executor/local.py`：_set_color_temp（按名称或代码），_set_rgb_gain（三通道）
- `mcp_server.py`：注册两个新工具
- 所有功能验证通过 ✅

### 3. USB Type-C RNDIS 文件传输

**发现 USB gadget**：板子 CH341 串口出现在 COM5，但无网络。
**启用 RNDIS**：`echo usb_rndis_en > /etc/init.d/.usb_config && usbdevice restart`
- 板子侧新增 `usb0` 接口，IP 169.254.184.100/16
- Windows 侧识别为"Remote NDIS based Internet Sharing Device"(以太网 4)
- 开机自启（systemd service + /etc/init.d/.usb_config）
- WiFi/以太网不受影响，两路共存

**文件传输验证**：通过 USB RNDIS pscp 传输 37KB PPTX ✅

### 4. 文件传输技能（file-transfer）

**从 Windows 视角→板子视角的转变**：
- 初版用 pscp/plink（Windows 命令），但 OpenClaw 跑在 Linux 板子上无法执行
- 最终方案：板子起 HTTP server → PC 浏览器/curl 下载
- 流程：`python3 -m http.server 8888` → 用户访问 `http://169.254.184.100:8888/文件`

**动态 IP 检测**（detect_board.ps1）：
- 找 RNDIS 网卡 → 推导 DHCP IP → 扫描子网 .2-.10
- USB 静态 IP 兜底
- 以太网最后尝试
- 输出 `board_connection.json`

**LLM 交互优化**：
- 核心原则："PC 拉，不是板子推"
- 禁止发明 HTTP/FTP 替代方案
- 标准化 SOP 流程

### 5. 外部技能安装

向 RK3576 板子 OpenClaw 安装了 3 个知识型技能：

| 技能 | 来源 | 用途 |
|------|------|------|
| `westockdata` | workbuddy skill_2053083170922696704 | A股/港股/美股行情数据 |
| `aihot` | workbuddy skill aihot | AI 中文资讯查询 |
| `tencent-news` | workbuddy skill_2053082907836022784 | 7×24 新闻搜索 |

安装方式：pscp 拷贝到 `~/.openclaw/workspace/skills/<name>/`，重启 gateway 自动加载。

### 6. 关键认知纠正

- **LLM 不能执行 Windows 命令**：OpenClaw 部署在 Linux 板子上，pscp/plink 不可用。之前的 SOP 写错了方向。
- **HDMI DDC/CI 双向可用**：之前误判"HDMI 不支持 DDC/CI"，实际测试证明双向切换都正常。
- **短音频识别差不是代码 bug**：麦克风灵敏度低 + STT 需要上下文，单字唤醒词识别困难。录整句后准确率完美。

## 今日提交（12 个 commit）

```
5a94185 fix(skill): rewrite for board-side execution
7fecb39 fix(skill): prevent LLM overthinking
bce7692 fix(file-transfer): USB RNDIS priority over ethernet
9976810 feat(file-transfer): dynamic IP detection
7bb7a24 docs(skill): rewrite file-transfer as SOP
7f8ac36 docs(skill): update file-transfer for USB RNDIS
42443a5 fix(file-transfer): detect USB RNDIS (169.254.184.100)
ca752f5 feat(skill): add file-transfer skill
1dad43f feat(ddcci): add color temp preset + RGB gain control
9d7b359 refactor(voice): v2 — record full utterance, STT once
476908f fix(voice): improve STT accuracy — align with voice_pipeline.py
1546fd6 docs: add 2026-06-23 daily report
```

## 待办

1. **推送分支**：`git push origin rk3576_lubancat`（80+ commits）
2. **麦克风外接**：板子自带 mic 灵敏度低，外接 3.5mm 麦克风可大幅提升识别
3. **list_apps 过滤优化**
4. **CosyVoice2 部署**：xinference 上缺少 TTS 模型
