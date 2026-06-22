# OpenClaw 集成设计 — iflyVoice 作为手肩

**状态**：Draft（待用户复核）
**日期**：2026-06-22
**分支**：`rk3576_lubancat`
**前置**：`2026-06-17-rk3576-port-design.md`（Plan 1/2/3 已完成基础移植）
**目标平台**：RK3576 鲁班猫，Ubuntu 22.04.5 LTS (GNU/Linux 6.1.99-rk3576 aarch64)

---

## 1. 背景与目标

### 1.1 现状

iflyVoice 在 RK3576 上的 Plan 1/2/3 已经把核心管线搬到板子：
- 板子端：widget.py / voice_pipeline.py / server.py + linux/ 适配器
- 远端 Win PC：执行 DDC-CI 显示器、桌面应用、B 站搜索（PC agent 接口契约已定义）

但**板子上没有 PC 代理实测落地**，widget.py 的桌面悬浮球 UI 在嵌入式场景下意义有限；同时 OpenClaw（v2026.6.6，commit 8c802aa）已经作为系统级 AI gateway 在板子上跑起来（systemd user service，端口 18789），拥有 WebSocket 协议、LLM 调度、工具调用、多渠道接入等完整能力。

**新问题**：OpenClaw 是"大脑"但没有"手"——它能对话、思考、规划，但调不了板子的硬件（亮度/音量/应用）。

### 1.2 集成目标

把 iflyVoice 改造为 **OpenClaw 的手肩**，让 OpenClaw 通过 iflyVoice 获得对 RK3576 板子的硬件控制能力。

**本期（Phase 1）范围**：
- 亮度调节（sysfs / xrandr）
- 音量调节（PulseAudio）
- 桌面应用控制（启动/关闭/切换/列出）
- OpenClaw 通过 `exec` 工具 + curl 调用 iflyVoice HTTP API
- SKILL.md 让 OpenClaw LLM 知道 iflyVoice 能做什么

**远期（不在本期）**：
- 语音 ASR/TTS（Phase 1.5）
- B 站搜索（Phase 1.5）
- OpenClaw Node 插件版（Phase 2）
- MCP server 化（Phase 3）
- 远端 Win PC 代理（待重新评估）

### 1.3 设计原则

1. **可移植性优先**：HTTP API + SKILL.md 是最便携的方案，未来换代理（Claude Code / Cursor）也能复用
2. **单一职责**：OpenClaw 负责对话与决策；iflyVoice 负责硬件执行
3. **保留抽象**：ExecutorDispatcher 路由不删 PC 路径，未来要切回只改配置
4. **降级优先**：每层失败必须有降级或可读错误给 LLM
5. **可观测**：所有 API 调用留日志，板子上能 tail

### 1.4 范围与非范围

**范围内**：
- iflyVoice HTTP 服务新增 8 个 tool 端点
- LocalExecutor 扩展（亮度/音量/应用三类 intent）
- SKILL.md + 软链到 `~/.openclaw/workspace/skills/iflyvoice/`
- ARM 板子 e2e 验证
- 启动脚本 `scripts/start-iflyvoice.sh`

**范围外**（本期不做）：
- widget.py 桌面悬浮球（停用但保留文件）
- 语音输入/输出（ASR/TTS）
- 远端 Win PC agent 实际部署
- OpenClaw 端 Node 插件
- MCP server 化
- B 站搜索

---

## 2. 架构

### 2.1 总体架构图

```
┌──────────────────────────────────────────────────────────────┐
│  RK3576 (aarch64 Ubuntu 22.04)                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  OpenClaw Gateway (Node.js) — 大脑                    │  │
│  │  · WebSocket :18789（已运行，pid 1235）                │  │
│  │  · LLM: minimax/MiniMax-M3                            │  │
│  │  · 内置 exec 工具 / Skills 加载器                      │  │
│  │  · 读 ~/.openclaw/workspace/skills/iflyvoice/SKILL.md │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │ exec(curl POST :18766/api/...)  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  iflyVoice (Python) — 手肩                            │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │ server.py — 新增 /api/v1/tools/* 路由           │   │  │
│  │  │   POST /tools/set_brightness | adjust_brightness│   │  │
│  │  │   POST /tools/set_volume    | adjust_volume     │   │  │
│  │  │   POST /tools/launch_app    | close_app | focus │   │  │
│  │  │   GET  /tools/list_apps                        │   │  │
│  │  │   GET  /health                                  │   │  │
│  │  └─────────────┬──────────────────────────────────┘   │  │
│  │                ▼                                       │  │
│  │  executor/dispatcher.py — 全 LOCAL 路由（本期）      │  │
│  │  executor/local.py — 真实实现（扩展）                  │  │
│  │    ├── SET_BRIGHTNESS  → linux/backlight.py           │  │
│  │    ├── SET_VOLUME      → linux/audio_io.py            │  │
│  │    └── LAUNCH_APP/...  → app_manager.py               │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 进程边界

| 进程 | 角色 | 端口 | 鉴权 |
|------|------|------|------|
| OpenClaw gateway | 接收消息、调 LLM、调度工具 | 18789 (WS) | token (OpenClaw 已有) |
| iflyVoice server | 提供 HTTP tool API | 18766 (HTTP, loopback) | 本期不鉴权（loopback only） |

**安全说明**：iflyVoice 绑 `127.0.0.1`，不暴露到 LAN。OpenClaw 与 iflyVoice 同机，无网络攻击面。

---

## 3. 组件与接口

### 3.1 iflyVoice HTTP API（新增）

**基础路径**：`http://127.0.0.1:18766`

**统一返回格式**（与 Executor 一致）：
```json
{"ok": true, "data": {...}}
{"ok": false, "err": "人类可读错误", "code": "ERR_XXX"}
```

| Method | Path | Body | 返回 | 说明 |
|--------|------|------|------|------|
| GET | `/health` | — | `{ok, version, uptime_s}` | 健康检查 |
| POST | `/api/v1/tools/set_brightness` | `{value: 0-100}` | `{ok, data: {value}}` | 设置绝对亮度 |
| POST | `/api/v1/tools/adjust_brightness` | `{delta: -100..100}` | `{ok, data: {value}}` | 增量调亮 |
| POST | `/api/v1/tools/set_volume` | `{value: 0-100}` | `{ok, data: {value}}` | 设置系统音量 |
| POST | `/api/v1/tools/adjust_volume` | `{delta: -100..100}` | `{ok, data: {value}}` | 增量调音量 |
| POST | `/api/v1/tools/launch_app` | `{name: "..."}` | `{ok, data: {pid, name}}` | 打开应用 |
| POST | `/api/v1/tools/close_app` | `{name: "..."}` | `{ok}` | 关闭应用 |
| POST | `/api/v1/tools/focus_app` | `{name: "..."}` | `{ok}` | 切换/聚焦应用 |
| GET | `/api/v1/tools/list_apps` | — | `{ok, data: [{name, pid, title}]}` | 列出已开应用 |
| GET | `/api/v1/tools/list_monitors` | — | `{ok, data: [{index, name, current_brightness}]}` | 列显示器 |

**错误码约定**：

| Code | 含义 |
|------|------|
| `ERR_BAD_REQUEST` | 缺少/非法参数 |
| `ERR_LOCAL_BACKLIGHT` | sysfs 写失败 / xrandr 失败 |
| `ERR_LOCAL_AUDIO` | PulseAudio 操作失败 |
| `ERR_APP_NOT_FOUND` | 应用名不在已知列表 |
| `ERR_APP_LAUNCH_FAILED` | 启动后未出现窗口 |
| `ERR_UNSUPPORTED` | LocalExecutor 不支持该 intent |

### 3.2 ExecutorDispatcher 路由调整

**改动**：`executor/dispatcher.py` 的 `_PC_INTENTS` 集合。

| Intent | 旧路由 | 新路由 | 备注 |
|--------|--------|--------|------|
| `SET_BRIGHTNESS` / `ADJUST_BRIGHTNESS` | pc_agent | **local** | 显示器控制统一在板子做 |
| `SET_CONTRAST` / `ADJUST_CONTRAST` / `SET_COLOR_TEMP` | pc_agent | **local** | 同上 |
| `SET_INPUT` / `LIST_INPUTS` | pc_agent | **local** | 同上 |
| `SET_VOLUME` / `ADJUST_VOLUME` | pc_agent | **local** | 音量走板子 |
| `LAUNCH_APP` / `CLOSE_APP` / `FOCUS_APP` / `LIST_APPS` | pc_agent | **local** | 应用走板子 |
| `BILIBILI_SEARCH` | pc_agent | （本期禁用） | 不在 MVP；返回 `ERR_UNSUPPORTED` |
| `SET_LOCAL_BACKLIGHT` / `ADJUST_LOCAL_BACKLIGHT` | local | local | 不变 |

**保留内容**：
- `PCAgentExecutor` 类和 `DevStubExecutor` 类保留
- 构造函数 `ExecutorDispatcher(pc_agent=..., dev_stub=..., local_executor=...)` 不变
- **本期不实例化** `pc_agent`，仅传 `local_executor`；设置 `pc_agent=None` 时 dispatcher 内部 fallback 到 local
- 未来要连 Win PC 时，改 `settings.json` 加 `winpc_agent_url` + 改 `_route()` 即可

### 3.3 LocalExecutor 新增方法

`executor/local.py` 需要补全的方法：

```python
class LocalExecutor:
    def execute(self, intent: Intent) -> dict:
        t = intent.type
        if t in (SET_BRIGHTNESS, ADJUST_BRIGHTNESS,
                 SET_CONTRAST, ADJUST_CONTRAST,
                 SET_COLOR_TEMP, SET_INPUT, LIST_INPUTS):
            return self._display(intent)
        elif t in (SET_VOLUME, ADJUST_VOLUME):
            return self._audio(intent)
        elif t in (LAUNCH_APP, CLOSE_APP, FOCUS_APP, LIST_APPS):
            return self._app(intent)
        elif t == BILIBILI_SEARCH:
            return {"ok": False, "err": "B站搜索本期不支持",
                    "code": "ERR_UNSUPPORTED"}
        else:
            return {"ok": False, "err": f"unsupported: {t.value}",
                    "code": "ERR_UNSUPPORTED"}
```

底层映射：
- `_display()` → `linux/backlight.py`（亮度）、`linux/display.py`（查询显示器）
- `_audio()` → `linux/audio_io.py`（音量 set/get）
- `_app()` → `app_manager.py`（启动/关闭/切换/列出）

**音频模块确认**：`linux/audio_io.py` 需扩展 `set_volume(percent)` 接口（现有只列设备）。如不支持需补实现（pulsectl）。

**应用模块确认**：`app_manager.py` 原本 Windows 专用（用 tasklist / WMIC），需重构或包装为 Linux 版本（用 wmctrl / xdotool / ps）。

### 3.4 OpenClaw 侧 SKILL.md

**位置**：`/home/cat/.openclaw/workspace/skills/iflyvoice/SKILL.md`

**内容**（概要）：
```markdown
---
name: iflyvoice
description: "控制 RK3576 板子的显示器亮度、系统音量、桌面应用。
  HTTP API 在 http://127.0.0.1:18766/api/v1/tools/。
  使用前确认 iflyVoice 服务在运行（curl http://127.0.0.1:18766/health）。"
---

# iflyVoice 硬件控制

iflyVoice 在 127.0.0.1:18766 提供 HTTP API。

## 可用能力
- 亮度：set_brightness(0-100), adjust_brightness(±n)
- 音量：set_volume(0-100), adjust_volume(±n)
- 应用：launch_app(name), close_app(name), focus_app(name), list_apps()

## 调用方式
用 exec 工具调 curl。例：
- 把亮度调到 60: `curl -X POST :18766/api/v1/tools/set_brightness -d '{"value":60}'`
- 音量 +10: `curl -X POST :18766/api/v1/tools/adjust_volume -d '{"delta":10}'`
- 打开浏览器: `curl -X POST :18766/api/v1/tools/launch_app -d '{"name":"浏览器"}'`

## 失败处理
返回 ok=false 时把 err 字段用自然语言告诉用户。
服务不通时提示先启动 iflyVoice。
```

完整 markdown 写到 `skills/iflyvoice/SKILL.md`，由 `install-arm64.sh` 软链/复制到 OpenClaw workspace。

### 3.5 启动 / 安装

**`scripts/start-iflyvoice.sh`**（新增）：
```bash
#!/bin/bash
# 启动 iflyVoice HTTP 服务（后台，绑 loopback）
set -e
cd "$(dirname "$0")/.."
exec python -m server --port 18766 --bind 127.0.0.1 \
  >> /var/log/iflyvoice.log 2>&1
```

**`scripts/install-arm64.sh`** 增加：
```bash
# 安装 iflyVoice skill 到 OpenClaw workspace
mkdir -p ~/.openclaw/workspace/skills/iflyvoice
cp $REPO_DIR/skills/iflyvoice/SKILL.md ~/.openclaw/workspace/skills/iflyvoice/
# 重启 OpenClaw 让 skill 生效
systemctl --user restart openclaw-gateway
```

**`settings.json`** 不需要改（如果之前已经走 local_executor）；如要显式禁用 PC 路径，加 `"winpc_agent_url": ""`。

---

## 4. 端到端数据流（实例）

用户对 OpenClaw 说："把屏幕调亮一点"：

```
1. OpenClaw WS 收到消息
2. LLM 读到 SKILL.md，知道 iflyVoice 可以调亮度
3. LLM 决定调亮度 +10，生成 tool call:
   exec: curl -X POST http://127.0.0.1:18766/api/v1/tools/adjust_brightness \
          -H "Content-Type: application/json" -d '{"delta":10}'
4. OpenClaw exec 工具执行 curl
5. iflyVoice server.py 收到请求
6. executor/dispatcher.dispatch(Intent(ADJUST_BRIGHTNESS, delta=10))
7. local._display() → linux/backlight.set_backlight_value(current + 10)
8. sysfs 写 /sys/class/backlight/<dev>/brightness
9. 返回 {"ok":true,"data":{"value":60}}
10. OpenClaw exec 返回 stdout 给 LLM
11. LLM 生成回复: "亮度已调到 60%"
12. (TTS 播报 — 本期不做，文字回复即可)
```

**用户能听到 OpenClaw 的文字回复**（OpenClaw 自带 TUI/WebUI 文字界面），语音播放等 Phase 1.5。

---

## 5. 错误处理

| 失败点 | 行为 |
|--------|------|
| iflyVoice 服务未起 | curl exit 7 → OpenClaw 提示"iflyVoice 服务未运行，请运行 start-iflyvoice.sh" |
| 亮度写 sysfs 失败（权限/无设备） | `ERR_LOCAL_BACKLIGHT` → LLM 回应"抱歉，无法调节亮度" |
| 音频设备不可用 | `ERR_LOCAL_AUDIO` → LLM 回应"未找到音频设备" |
| 应用名不在 app_manager 列表 | `ERR_APP_NOT_FOUND` → LLM 回应"找不到 XX，可用的有 ..." |
| 应用启动后未出现窗口 | `ERR_APP_LAUNCH_FAILED` → LLM 回应"启动 XX 后未检测到窗口" |
| OpenClaw exec 解析失败 | 把原始 stderr 给 LLM |
| B 站搜索 | `ERR_UNSUPPORTED` → LLM 回应"暂不支持" |

**降级原则**：任何硬件操作失败都不应让 OpenClaw 进程崩溃；错误必须以 JSON 格式回到 LLM，由 LLM 用自然语言表达。

---

## 6. 测试策略

### 6.1 单元测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_local_executor.py` | LocalExecutor 新增的 4 类 intent |
| `tests/test_server_tools.py` | 8 个 HTTP 端点的请求/响应 |

### 6.2 集成测试（ARM 板子）

**`scripts/e2e_iflyvoice.sh`**（新增）：
```bash
#!/bin/bash
set -e
# 1. 启动 iflyVoice
bash scripts/start-iflyvoice.sh &
sleep 2
# 2. 健康检查
curl -fsS http://127.0.0.1:18766/health
# 3. 调亮度
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/set_brightness \
  -H "Content-Type: application/json" -d '{"value":50}'
# 4. 验证 sysfs
grep -q "^100$" /sys/class/backlight/*/brightness  # 50% 对应 raw
# 5. 调音量
curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/set_volume \
  -H "Content-Type: application/json" -d '{"value":30}'
# 6. 列应用
curl -fsS http://127.0.0.1:18766/api/v1/tools/list_apps
# 7. 错误路径
! curl -fsS -X POST http://127.0.0.1:18766/api/v1/tools/launch_app \
  -H "Content-Type: application/json" -d '{"name":"不存在的应用"}'
echo "[OK] e2e_iflyvoice passed"
```

### 6.3 LLM 链路测试（ARM 板子）

**`scripts/e2e_openclaw_iflyvoice.sh`**（新增）：
```bash
#!/bin/bash
set -e
# 通过 openclaw CLI 模拟用户消息，看 LLM 是否真的调通 iflyVoice
# 1. 记下当前亮度
INIT=$(cat /sys/class/backlight/*/brightness)
# 2. 给 OpenClaw 发"把亮度调到 75"
openclaw agent --message "把亮度调到 75" --thinking low
sleep 3
# 3. 验证 sysfs 真的被改
NEW=$(cat /sys/class/backlight/*/brightness)
[ "$NEW" -ne "$INIT" ] || { echo "亮度没变"; exit 1; }
echo "[OK] openclaw->iflyvoice 链路通"
```

### 6.4 板子验证门禁

复用 Plan 3 的 `scripts/check_arm64.sh` + `tests/bench_arm64.py`，新增：
- `bash scripts/e2e_iflyvoice.sh`
- `bash scripts/e2e_openclaw_iflyvoice.sh`

全部通过才视为 Phase 1 完成。

---

## 7. 实施步骤（高层）

1. **LocalExecutor 扩展**：补 `_display / _audio / _app` 三个方法；补 `linux/audio_io.set_volume`；重构 `app_manager.py` 为 Linux 版本
2. **server.py 新增 tools 路由**：8 个端点 + `/health`；统一异常处理
3. **dispatcher 路由调整**：`_PC_INTENTS` 改为 `_LOCAL_INTENTS`；处理 `pc_agent=None` 的边界
4. **SKILL.md 编写**：在 `skills/iflyvoice/SKILL.md`；描述能力 + curl 示例
5. **启动脚本**：`scripts/start-iflyvoice.sh` + `install-arm64.sh` 加 skill 安装段
6. **测试**：单元 + e2e 脚本
7. **板子端到端**：手动 + 自动脚本验证

---

## 8. 风险与开放问题

| 风险 | 缓解 |
|------|------|
| 板子 X11/Wayland 桌面未运行 | 启动脚本检查 `$DISPLAY`；如无则跳过应用控制相关测试 |
| PulseAudio 服务未起 | 音量操作返回 `ERR_LOCAL_AUDIO` 即可，不影响其他能力 |
| 应用列表为空（板子是裸系统） | `app_manager` 提供一个内置白名单 + `xdg-open` 兜底 |
| LLM 调 curl 路径错误（漏引号、参数错） | SKILL.md 给完整可复制 curl 命令 |
| OpenClaw 加载 SKILL.md 失败 | `install-arm64.sh` 加验证（curl 健康检查 + 文件存在检查） |
| app_manager.py 重构量大 | 先做基础 4 个操作（launch/close/focus/list），复杂 UI 自动化下期 |

---

## 9. 变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-22 | v0.1 | 初稿：架构 + 接口 + 测试 + 风险（待用户复核） |

---

## 10. 相关文档

- 前置：`docs/superpowers/specs/2026-06-17-rk3576-port-design.md`
- API 契约：`docs/WIN_PC_AGENT_API.md`（已存在，本期不使用但保留）
- 实施计划：将由 `writing-plans` 阶段产出
