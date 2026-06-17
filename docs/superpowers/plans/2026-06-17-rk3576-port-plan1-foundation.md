# RK3576 Port — Plan 1: 架构基座 (Architectural Foundation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 RK3576 移植的架构基座：executor 抽象层 + server /native 路由 + Win PC Agent HTTP 接口契约 + Linux 依赖与预检脚本。让核心架构在 x86 上能跑通单元测试，无需板子。

**Architecture:**
- `executor/base.py` 定义意图→方法契约（ABC）
- `executor/pc_agent.py` HTTP 客户端调 Win PC（产品态）
- `executor/dev_stub.py` 假实现（无 PC 时也能跑测试）
- `server.py` 新增 `/native`（调本机屏软调），删除 DDC-CI / WMI
- `docs/WIN_PC_AGENT_API.md` 写明 Win PC agent 的 HTTP 契约

**Tech Stack:** Python 3.10+, pytest, responses (HTTP mock), tenacity, requests, pydantic

**Reference spec:** `docs/superpowers/specs/2026-06-17-rk3576-port-design.md`

**后续 plans：**
- Plan 2: Linux 用户面移植（audio_io / widget / voice_pipeline）— 需要板子
- Plan 3: NPU 接入 + ARM 验证门禁 — 需要板子 + RKNN

---

## 文件结构（Plan 1 涉及）

```
iflyVoice/
├── executor/                  # 🆕
│   ├── __init__.py
│   ├── base.py                # Executor ABC
│   ├── pc_agent.py            # HTTP 客户端
│   └── dev_stub.py            # 假实现
│
├── server.py                  # 改：删 DDC-CI/WMI、加 /native
├── settings.json              # 改：加 winpc_agent_url / npu_asr_enabled
│
├── docs/
│   └── WIN_PC_AGENT_API.md    # 🆕 HTTP 接口契约
│
├── requirements-arm64.txt     # 🆕 依赖清单
├── install-arm64.sh           # 🆕 一键装环境
├── scripts/
│   ├── check_arm64.sh         # 🆕 启动前预检
│   └── run_all_arm64.sh       # 🆕 一键跑全测
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_executor_base.py
    ├── test_pc_agent.py
    └── test_server.py
```

---

## Phase 0: 项目结构 & 依赖基线

### Task 0.1: 创建新目录结构

**Files:**
- Create: `executor/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `scripts/.gitkeep`
- Create: `docs/WIN_PC_AGENT_API.md` (placeholder, full content in Task 0.3)
- Create: `requirements-arm64.txt`
- Create: `install-arm64.sh`

- [ ] **Step 1: 创建空目录占位文件**

```bash
mkdir -p executor tests scripts docs
touch executor/__init__.py
touch tests/__init__.py
touch tests/conftest.py
touch scripts/.gitkeep
```

- [ ] **Step 2: 创建 requirements-arm64.txt**

写入 `requirements-arm64.txt`：
```
# Core UI
PySide6>=6.6
sounddevice>=0.4.6

# Audio / ML
numpy>=1.24
onnxruntime>=1.17
requests>=2.31
edge-tts>=6.1
Pillow>=10.0

# Linux 音频
pulsectl>=1.0
pyalsaaudio>=0.10

# NPU 推理（板子跑才需要，x86 上 install 时跳过）
rknn-toolkit2-lite2>=2.0; sys_platform == "linux" and platform_machine == "aarch64"

# Robustness
tenacity>=8.2
pydantic>=2.5

# Dev / Test
pytest>=7.4
responses>=0.24
psutil>=5.9
```

- [ ] **Step 3: 创建 install-arm64.sh**

写入 `install-arm64.sh`：
```bash
#!/bin/bash
# 在 RK3576 (Ubuntu 22.04 aarch64) 上跑：bash install-arm64.sh
set -e

echo "[1/4] 系统依赖"
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv \
    pulseaudio pulseaudio-utils \
    alsa-utils \
    ffmpeg \
    fonts-noto-cjk \
    libxcb-cursor0 libxkbcommon-x11-0 \
    i2c-tools

echo "[2/4] Python 虚拟环境"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

echo "[3/4] Python 依赖"
pip install -r requirements-arm64.txt

echo "[4/4] 完成"
echo "激活 venv: source .venv/bin/activate"
echo "预检环境:  bash scripts/check_arm64.sh"
```

- [ ] **Step 4: 提交**

```bash
git add executor/ tests/ scripts/ docs/ requirements-arm64.txt install-arm64.sh
git commit -m "feat(port): scaffold executor/ tests/ scripts/ dirs + ARM64 deps"
```

---

### Task 0.2: settings.json 扩展

**Files:**
- Modify: `settings.json`

- [ ] **Step 1: 读取现有 settings.json 并加新字段**

读取现有 `settings.json` 内容（本例假设已存在）然后加入两个字段：
```json
{
  "mic_device": "",
  "mute_tts": false,
  "audio_url": "http://192.168.1.32:9997",
  "ollama_url": "http://192.168.1.32:11434",
  "ollama_model": "qwen3-vl:2b",
  "wake_word": "小爱同学",
  "logo_path": "",
  "winpc_agent_url": "http://192.168.1.50:18770",
  "npu_asr_enabled": true,
  "use_local_executor": false
}
```

新字段说明：
- `winpc_agent_url`: Win PC agent 的 HTTP 服务地址（产品态）
- `npu_asr_enabled`: 是否启用 NPU 本地 ASR（关闭则走 audio_url 远端）
- `use_local_executor`: 是否走 dev_stub（仅 dev/单测用，**生产必须 false**）

- [ ] **Step 2: 提交**

```bash
git add settings.json
git commit -m "feat(port): add winpc_agent_url + npu_asr_enabled + use_local_executor to settings"
```

---

### Task 0.3: Win PC Agent API 契约文档

**Files:**
- Create: `docs/WIN_PC_AGENT_API.md`

- [ ] **Step 1: 写入完整 API 契约**

写入 `docs/WIN_PC_AGENT_API.md`：
```markdown
# Win PC Agent HTTP API 契约 (v0.1)

> **状态**：Draft — Plan 1 仅写契约，**实现放下一期**。
> RK3576 端 `executor/pc_agent.py` 按本契约调用。
> Win PC 端用 Python+pywin32 实现 agent.exe（HTTP 服务 + 现有 DDC-CI / app_manager / B 站代码）。

## 通用约定

- **协议**：HTTP/1.1，端口默认 `18770`
- **Content-Type**: `application/json; charset=utf-8`
- **字符集**: UTF-8
- **超时**: 3s（executor 内部用 `tenacity` 重试 3 次：1s/2s/4s 退避）

## 统一响应格式

成功：
```json
{"ok": true, "data": {...}}
```

失败：
```json
{"ok": false, "err": "人类可读错误描述", "code": "ERR_XXX"}
```

错误码：
- `ERR_DISPLAY_NOT_FOUND` — 找不到指定显示器
- `ERR_DDCCI_UNSUPPORTED` — 显示器不支持 DDC-CI
- `ERR_APP_NOT_FOUND` — 找不到应用
- `ERR_APP_LAUNCH_FAILED` — 启动应用失败
- `ERR_BILIBILI_API_FAILED` — B 站 API 调用失败
- `ERR_INTERNAL` — 内部错误

## 端点

### 健康检查

`GET /health`

响应：
```json
{"ok": true, "version": "0.1.0"}
```

### 显示器枚举

`GET /monitors`

响应：
```json
{
  "ok": true,
  "data": {
    "monitors": [
      {"index": 0, "name": "DELL U2723QE", "supports_ddcci": true, "current_input": "HDMI1"}
    ]
  }
}
```

### 显示器控制

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| POST | `/display/brightness` | `{"value": 0-100}` | `{"actual": 50, "restored": false}` |
| POST | `/display/contrast` | `{"value": 0-100}` | `{"actual": 50}` |
| POST | `/display/color_temp` | `{"value": 0-100, "monitor_index": 0}` | `{"actual": 50}` |
| GET | `/display/color_temp` | - | `{"value": 50}` |
| GET | `/display/inputs` | `?monitor_index=0` | `{"current": "HDMI1", "supported": [{"code": 17, "name": "HDMI1"}, ...]}` |
| POST | `/display/input` | `{"code": 17, "monitor_index": 0}` | `{"name": "HDMI1", "old_name": "DP1", "restored": false}` |

### 音量

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| GET | `/volume` | - | `{"value": 50}` |
| POST | `/volume` | `{"value": 0-100}` | `{"actual": 50}` |

### 桌面应用

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| GET | `/apps/installed` | - | `{"apps": [{"name": "微信", "path": "..."}]}` |
| GET | `/apps/running` | - | `{"windows": [{"hwnd": 12345, "title": "微信", "pid": 6789}]}` |
| POST | `/apps/launch` | `{"name": "微信"}` | `{"pid": 6789}` |
| POST | `/apps/close` | `{"name": "微信"}` 或 `{"hwnd": 12345}` | `{}` |
| POST | `/apps/focus` | `{"name": "微信"}` 或 `{"hwnd": 12345}` | `{}` |

### B 站

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| GET | `/bilibili/search` | `?keyword=Python 教程` | `{"results": [{"bvid": "BV1xx", "title": "...", "author": "...", "duration": 600}]}` |
| POST | `/bilibili/play` | `{"bvid": "BV1xx"}` | `{"title": "..."}` |

## 安全

- 内网使用，无需鉴权（v0.1）
- v0.2 加 `Authorization: Bearer <token>` 头

## 版本

- v0.1: 2026-06-17 初稿
```

- [ ] **Step 2: 提交**

```bash
git add docs/WIN_PC_AGENT_API.md
git commit -m "docs(port): add Win PC Agent HTTP API contract v0.1"
```

---

### Task 0.4: check_arm64.sh 预检脚本

**Files:**
- Create: `scripts/check_arm64.sh`

- [ ] **Step 1: 写入预检脚本**

写入 `scripts/check_arm64.sh`：
```bash
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
```

- [ ] **Step 2: 加执行权限并提交**

```bash
chmod +x scripts/check_arm64.sh
git add scripts/check_arm64.sh
git commit -m "feat(port): add check_arm64.sh preflight script"
```

---

## Phase 1: Executor 抽象层

### Task 1.1: Executor ABC + 意图映射

**Files:**
- Create: `executor/base.py`
- Test: `tests/test_executor_base.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_executor_base.py`：
```python
import pytest
from executor.base import Executor, Intent, IntentType, ExecutorError


def test_intent_construction():
    """Intent 数据类能正确构造和序列化"""
    i = Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0})
    assert i.type == IntentType.SET_BRIGHTNESS
    assert i.params == {"value": 50, "monitor_index": 0}
    assert i.to_dict() == {
        "type": "set_brightness",
        "params": {"value": 50, "monitor_index": 0},
    }


def test_executor_abc_cannot_instantiate():
    """Executor 是抽象类，不能直接实例化"""
    with pytest.raises(TypeError):
        Executor()


def test_parse_display_intent_brightness_set():
    """从意图文本解析 set_brightness"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("亮度设为50")
    assert intent is not None
    assert intent.type == IntentType.SET_BRIGHTNESS
    assert intent.params["value"] == 50


def test_parse_display_intent_brightness_adjust():
    """从意图文本解析 adjust_brightness"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("亮度调高10")
    assert intent is not None
    assert intent.type == IntentType.ADJUST_BRIGHTNESS
    assert intent.params["delta"] == 10


def test_parse_volume_intent():
    """从意图文本解析音量"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("音量调到30")
    assert intent is not None
    assert intent.type == IntentType.SET_VOLUME
    assert intent.params["value"] == 30


def test_parse_app_launch_intent():
    """从意图文本解析打开应用"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("打开微信")
    assert intent is not None
    assert intent.type == IntentType.LAUNCH_APP
    assert intent.params["name"] == "微信"


def test_parse_bilibili_intent():
    """从意图文本解析 B 站搜索"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("B站搜索 Python 教程")
    assert intent is not None
    assert intent.type == IntentType.BILIBILI_SEARCH
    assert intent.params["keyword"] == "Python 教程"


def test_parse_local_screen_intent():
    """从意图文本解析本机屏控制"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("本机屏幕亮一点")
    assert intent is not None
    assert intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT
    assert intent.params["delta"] == 10
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_executor_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'executor.base'`

- [ ] **Step 3: 实现 Executor ABC**

写入 `executor/base.py`：
```python
"""Executor 抽象层 — 业务侧只调接口，不感知 local/remote"""
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class IntentType(str, Enum):
    """所有可执行意图的类型枚举"""
    # 显示器控制（远端 PC 显示器）
    SET_BRIGHTNESS = "set_brightness"
    ADJUST_BRIGHTNESS = "adjust_brightness"
    SET_CONTRAST = "set_contrast"
    ADJUST_CONTRAST = "adjust_contrast"
    SET_COLOR_TEMP = "set_color_temp"
    SET_INPUT = "set_input"
    LIST_INPUTS = "list_inputs"

    # 音量（远端 PC 系统音量）
    SET_VOLUME = "set_volume"
    ADJUST_VOLUME = "adjust_volume"

    # 桌面应用（远端 PC）
    LAUNCH_APP = "launch_app"
    CLOSE_APP = "close_app"
    FOCUS_APP = "focus_app"
    LIST_APPS = "list_apps"

    # B 站搜索（远端 PC ffplay 播）
    BILIBILI_SEARCH = "bilibili_search"

    # 本机控制（RK3576 本地，不走 PC）
    ADJUST_LOCAL_BACKLIGHT = "adjust_local_backlight"
    SET_LOCAL_BACKLIGHT = "set_local_backlight"

    # 无意图（普通对话）
    NONE = "none"


@dataclass
class Intent:
    """意图数据类 — 业务侧产出，executor 消费"""
    type: IntentType
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


class ExecutorError(Exception):
    """执行器统一异常"""
    pass


class Executor(ABC):
    """执行器抽象基类。子类：pc_agent（生产）、dev_stub（测试）"""

    @abstractmethod
    def execute(self, intent: Intent) -> dict:
        """执行意图，返回 {"ok": bool, ...}

        成功：{"ok": True, "data": {...}}
        失败：{"ok": False, "err": "...", "code": "ERR_XXX"}
        """
        raise NotImplementedError

    def execute_safe(self, intent: Intent) -> dict:
        """执行意图，捕获异常并包装为标准错误格式"""
        try:
            return self.execute(intent)
        except ExecutorError as e:
            return {"ok": False, "err": str(e), "code": "ERR_INTERNAL"}
        except Exception as e:
            return {"ok": False, "err": str(e), "code": "ERR_INTERNAL"}


# ── 文本→意图 解析 ─────────────────────────────────────
# 复用现有 voice_pipeline.parse_voice_command 的正则逻辑，但产出 Intent 而非 dict

_DISPLAY_CONTROL_MAP = {
    "brightness": IntentType.SET_BRIGHTNESS,
    "contrast": IntentType.SET_CONTRAST,
    "color_temp": IntentType.SET_COLOR_TEMP,
}


def parse_intent_from_voice_text(text: str) -> Optional[Intent]:
    """从 ASR 文本解析意图。返回 Intent 或 None（普通对话）。"""
    if not text:
        return None
    t = text.lower().strip()

    # ── 本机屏控制（明确说"本机/自己"） ──
    if re.search(r'(?:本机|自己|这个)(?:屏幕|显示器|屏).*(?:亮一点|再亮点|更亮|亮一些)', t):
        return Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 10})
    if re.search(r'(?:本机|自己|这个)(?:屏幕|显示器|屏).*(?:暗一点|再暗点|更暗|暗一些)', t):
        return Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": -10})

    # ── 亮度 ──
    m = re.search(r'(?:把\s*)?亮度\s*(?:调|设)(?:高|大|亮|低|小|暗)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
    if not m:
        m = re.search(r'(?:亮度|屏幕)\s*[:：]?\s*(\d{1,3})%?', t)
    if m:
        v = max(0, min(100, int(m.group(1))))
        return Intent(IntentType.SET_BRIGHTNESS, {"value": v, "monitor_index": 0})

    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大|最亮|full)', t):
        return Intent(IntentType.SET_BRIGHTNESS, {"value": 100, "monitor_index": 0})
    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小|最暗)', t):
        return Intent(IntentType.SET_BRIGHTNESS, {"value": 0, "monitor_index": 0})

    m = re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:高|大|亮)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_BRIGHTNESS, {"delta": int(m.group(1)), "monitor_index": 0})
    m = re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:低|小|暗)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_BRIGHTNESS, {"delta": -int(m.group(1)), "monitor_index": 0})

    # ── 音量 ──
    m = re.search(r'音量\s*(?:调|设)(?:高|大|低|小)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
    if m:
        return Intent(IntentType.SET_VOLUME, {"value": max(0, min(100, int(m.group(1))))})
    m = re.search(r'音量\s*(?:调|设)?(?:高|大)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_VOLUME, {"delta": int(m.group(1))})
    m = re.search(r'音量\s*(?:调|设)?(?:低|小)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_VOLUME, {"delta": -int(m.group(1))})
    if re.search(r'音量.*(?:大点|大一些|大声|大声点)', t):
        return Intent(IntentType.ADJUST_VOLUME, {"delta": 10})
    if re.search(r'音量.*(?:小点|小一些|小声|小声点)', t):
        return Intent(IntentType.ADJUST_VOLUME, {"delta": -10})

    # ── 应用控制 ──
    m = re.search(r'打开\s*(.+)', t)
    if m:
        return Intent(IntentType.LAUNCH_APP, {"name": m.group(1).strip()})
    m = re.search(r'关闭\s*(.+)', t)
    if m:
        return Intent(IntentType.CLOSE_APP, {"name": m.group(1).strip()})
    m = re.search(r'切换到\s*(.+)', t)
    if m:
        return Intent(IntentType.FOCUS_APP, {"name": m.group(1).strip()})

    # ── B 站 ──
    m = re.search(r'(?:搜索|找|播放|听)(?:.*?)?(?:B站|哔哩哔哩|bilibili|b站)(?:.*?)?(.+)', t)
    if m:
        kw = m.group(1).strip()
        if kw:
            return Intent(IntentType.BILIBILI_SEARCH, {"keyword": kw})
    m = re.search(r'(?:B站|哔哩哔哩|bilibili|b站)\s*(.+)', t)
    if m:
        kw = m.group(1).strip()
        if kw and not re.search(r'打开|关闭', kw):
            return Intent(IntentType.BILIBILI_SEARCH, {"keyword": kw})

    return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_executor_base.py -v
```

Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add executor/base.py tests/test_executor_base.py
git commit -m "feat(executor): add ABC + Intent + parse_intent_from_voice_text"
```

---

### Task 1.2: dev_stub 执行器

**Files:**
- Create: `executor/dev_stub.py`
- Test: `tests/test_executor_base.py` (扩展)

- [ ] **Step 1: 扩展测试**

追加到 `tests/test_executor_base.py`：
```python
from executor.dev_stub import DevStubExecutor


def test_dev_stub_set_brightness():
    """dev_stub 能处理 set_brightness"""
    exe = DevStubExecutor()
    result = exe.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["actual"] == 50
    assert "fake" in result["data"]["note"]


def test_dev_stub_launch_app():
    """dev_stub 能处理 launch_app"""
    exe = DevStubExecutor()
    result = exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "微信"}))
    assert result["ok"] is True
    assert result["data"]["name"] == "微信"


def test_dev_stub_local_backlight_records_state():
    """dev_stub 维护本机屏状态的内部字典"""
    exe = DevStubExecutor()
    exe.execute_safe(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 10}))
    exe.execute_safe(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 20}))
    state = exe.get_local_state()
    assert state["backlight"] == 30
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_executor_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'executor.dev_stub'`

- [ ] **Step 3: 实现 DevStubExecutor**

写入 `executor/dev_stub.py`：
```python
"""dev_stub 执行器 — 仅用于 dev/单测，永远不会用于生产"""
from __future__ import annotations
from typing import Any
from executor.base import Executor, Intent, IntentType


class DevStubExecutor(Executor):
    """假实现：记录调用、维护一个内部状态、返回固定 ok。
    用于：
      - 单测（验证业务逻辑是否正确调度了 executor）
      - 离线开发（没 Win PC 时让 voice_pipeline 跑得通）
    """

    def __init__(self):
        self._local_state = {
            "backlight": 50,
        }
        self._call_log: list[dict] = []

    def execute(self, intent: Intent) -> dict:
        self._call_log.append(intent.to_dict())

        if intent.type == IntentType.SET_BRIGHTNESS:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake pc_agent"}}

        if intent.type == IntentType.ADJUST_BRIGHTNESS:
            return {"ok": True, "data": {"delta": intent.params["delta"], "note": "fake pc_agent"}}

        if intent.type == IntentType.SET_CONTRAST:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake"}}

        if intent.type == IntentType.ADJUST_CONTRAST:
            return {"ok": True, "data": {"delta": intent.params["delta"], "note": "fake"}}

        if intent.type == IntentType.SET_COLOR_TEMP:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake"}}

        if intent.type == IntentType.SET_INPUT:
            return {"ok": True, "data": {"name": f"0x{intent.params.get('code', 0):02X}", "note": "fake"}}

        if intent.type == IntentType.LIST_INPUTS:
            return {"ok": True, "data": {"current": "HDMI1", "supported": ["HDMI1", "DP1"], "note": "fake"}}

        if intent.type == IntentType.SET_VOLUME:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake"}}

        if intent.type == IntentType.ADJUST_VOLUME:
            return {"ok": True, "data": {"delta": intent.params["delta"], "note": "fake"}}

        if intent.type == IntentType.LAUNCH_APP:
            return {"ok": True, "data": {"name": intent.params["name"], "pid": 99999, "note": "fake"}}

        if intent.type == IntentType.CLOSE_APP:
            return {"ok": True, "data": {"name": intent.params.get("name", ""), "note": "fake"}}

        if intent.type == IntentType.FOCUS_APP:
            return {"ok": True, "data": {"name": intent.params.get("name", ""), "note": "fake"}}

        if intent.type == IntentType.LIST_APPS:
            return {"ok": True, "data": {"apps": [{"name": "微信", "path": "/fake/wechat.exe"}], "note": "fake"}}

        if intent.type == IntentType.BILIBILI_SEARCH:
            return {"ok": True, "data": {"results": [{"bvid": "BV_FAKE", "title": f"fake: {intent.params.get('keyword', '')}"}], "note": "fake"}}

        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            self._local_state["backlight"] = max(0, min(100, self._local_state["backlight"] + intent.params["delta"]))
            return {"ok": True, "data": {"actual": self._local_state["backlight"]}}

        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            self._local_state["backlight"] = max(0, min(100, intent.params["value"]))
            return {"ok": True, "data": {"actual": self._local_state["backlight"]}}

        return {"ok": False, "err": f"dev_stub 不支持 {intent.type.value}", "code": "ERR_INTERNAL"}

    def get_local_state(self) -> dict:
        return dict(self._local_state)

    def get_call_log(self) -> list[dict]:
        return list(self._call_log)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_executor_base.py -v
```

Expected: 10 passed

- [ ] **Step 5: 提交**

```bash
git add executor/dev_stub.py tests/test_executor_base.py
git commit -m "feat(executor): add DevStubExecutor for dev/test"
```

---

### Task 1.3: pc_agent HTTP 客户端（带重试）

**Files:**
- Create: `executor/pc_agent.py`
- Test: `tests/test_pc_agent.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_pc_agent.py`：
```python
import pytest
import responses
from executor.pc_agent import PCAgentExecutor
from executor.base import Intent, IntentType, ExecutorError


@pytest.fixture
def pc():
    return PCAgentExecutor(base_url="http://pc.local:18770", timeout=1.0, max_retries=2)


@responses.activate
def test_set_brightness_success(pc):
    """set_brightness 成功路径"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": True, "data": {"actual": 50}},
        status=200,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["actual"] == 50
    assert len(responses.calls) == 1


@responses.activate
def test_set_brightness_retries_on_5xx(pc):
    """5xx 触发重试，最终失败返回标准错误"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "boom"},
        status=500,
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "boom"},
        status=500,
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "boom"},
        status=500,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is False
    assert result["code"] == "ERR_INTERNAL"
    assert len(responses.calls) == 3  # max_retries=2 → 3 次总尝试


@responses.activate
def test_set_brightness_recovers_on_retry(pc):
    """第一次 5xx，第二次成功"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "transient"},
        status=503,
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": True, "data": {"actual": 60}},
        status=200,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 60, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["actual"] == 60
    assert len(responses.calls) == 2


@responses.activate
def test_set_brightness_timeout_treated_as_failure(pc):
    """连接超时算失败，进入重试"""
    import requests as real_requests
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body=real_requests.exceptions.Timeout(),
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body=real_requests.exceptions.Timeout(),
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body=real_requests.exceptions.Timeout(),
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is False
    assert "PC" in result["err"] or "timeout" in result["err"].lower()


@responses.activate
def test_launch_app_pc_returns_4xx(pc):
    """PC 端业务错误（4xx）不重试，直接透传"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/apps/launch",
        json={"ok": False, "err": "找不到应用", "code": "ERR_APP_NOT_FOUND"},
        status=404,
    )
    result = pc.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "不存在的app"}))
    assert result["ok"] is False
    assert result["code"] == "ERR_APP_NOT_FOUND"
    assert len(responses.calls) == 1  # 4xx 不重试


@responses.activate
def test_health_check(pc):
    """健康检查返回 True/False"""
    responses.add(responses.GET, "http://pc.local:18770/health", json={"ok": True, "version": "0.1"}, status=200)
    assert pc.health_check() is True

    responses.reset()
    responses.add(responses.GET, "http://pc.local:18770/health", json={"ok": False}, status=500)
    assert pc.health_check() is False
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pip install responses
pytest tests/test_pc_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'executor.pc_agent'`

- [ ] **Step 3: 实现 PCAgentExecutor**

**只用最终版（不要用中间版）**——把以下完整内容写入 `executor/pc_agent.py`：

```python
"""pc_agent 执行器 — HTTP 客户端调 Win PC agent
符合 docs/WIN_PC_AGENT_API.md v0.1 契约
"""
from __future__ import annotations
import time
from typing import Optional
import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type
)
from executor.base import Executor, Intent, IntentType, ExecutorError


_RETRYABLE_HTTP = (500, 502, 503, 504, 429)


class PCAgentError(ExecutorError):
    pass


def _is_retryable_response(resp: requests.Response) -> bool:
    return resp.status_code in _RETRYABLE_HTTP


def _is_business_error(resp: requests.Response) -> bool:
    return 400 <= resp.status_code < 500 and resp.status_code != 429


def _do_http_with_retry(method: str, url: str, *, params=None, json_body=None, timeout: float = 3.0, max_attempts: int = 3) -> dict:
    """带重试的 HTTP 调用。重试：5xx/429/timeout/连接错误，指数退避 1s/2s/4s。"""
    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            PCAgentError,
        )),
        reraise=True,
    )
    def _inner():
        try:
            if method == "GET":
                resp = requests.get(url, params=params, timeout=timeout)
            else:
                resp = requests.post(url, json=json_body, timeout=timeout)
        except requests.exceptions.Timeout as e:
            raise PCAgentError(f"timeout: {e}") from e
        except requests.exceptions.ConnectionError as e:
            raise PCAgentError(f"connection: {e}") from e

        if _is_business_error(resp):
            try:
                return resp.json()
            except Exception:
                return {"ok": False, "err": f"PC 返回 {resp.status_code}", "code": "ERR_INTERNAL"}

        if _is_retryable_response(resp):
            raise PCAgentError(f"retryable status {resp.status_code}")

        try:
            return resp.json()
        except Exception as e:
            raise PCAgentError(f"invalid json: {e}") from e

    return _inner()


class PCAgentExecutor(Executor):
    """HTTP 客户端 executor，对接 Win PC agent.exe"""

    def __init__(self, base_url: str, timeout: float = 3.0, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0

    _ROUTES = {
        IntentType.SET_BRIGHTNESS:       ("POST", "/display/brightness",     ["value", "monitor_index"]),
        IntentType.ADJUST_BRIGHTNESS:     ("POST", "/display/brightness",     ["delta", "monitor_index"]),
        IntentType.SET_CONTRAST:         ("POST", "/display/contrast",       ["value", "monitor_index"]),
        IntentType.ADJUST_CONTRAST:      ("POST", "/display/contrast",       ["delta", "monitor_index"]),
        IntentType.SET_COLOR_TEMP:       ("POST", "/display/color_temp",     ["value", "monitor_index"]),
        IntentType.SET_INPUT:            ("POST", "/display/input",          ["code", "monitor_index"]),
        IntentType.LIST_INPUTS:          ("GET",  "/display/inputs",         ["monitor_index"]),
        IntentType.SET_VOLUME:           ("POST", "/volume",                 ["value"]),
        IntentType.ADJUST_VOLUME:        ("POST", "/volume",                 ["delta"]),
        IntentType.LAUNCH_APP:           ("POST", "/apps/launch",            ["name"]),
        IntentType.CLOSE_APP:            ("POST", "/apps/close",             ["name"]),
        IntentType.FOCUS_APP:            ("POST", "/apps/focus",             ["name"]),
        IntentType.LIST_APPS:            ("GET",  "/apps/installed",         []),
        IntentType.BILIBILI_SEARCH:      ("GET",  "/bilibili/search",        ["keyword"]),
    }

    def execute(self, intent: Intent) -> dict:
        route = self._ROUTES.get(intent.type)
        if not route:
            return {"ok": False, "err": f"pc_agent 不支持意图 {intent.type.value}", "code": "ERR_INTERNAL"}

        method, path, param_keys = route
        params = {k: intent.params[k] for k in param_keys if k in intent.params}
        url = f"{self.base_url}{path}"

        try:
            if method == "GET":
                result = _do_http_with_retry("GET", url, params=params,
                                              timeout=self.timeout, max_attempts=self.max_retries + 1)
            else:
                result = _do_http_with_retry("POST", url, json_body=params,
                                              timeout=self.timeout, max_attempts=self.max_retries + 1)
        except PCAgentError as e:
            self._record_failure()
            return {"ok": False, "err": f"PC agent 不可达：{e}", "code": "ERR_INTERNAL"}
        except Exception as e:
            self._record_failure()
            return {"ok": False, "err": f"调用 PC 异常：{e}", "code": "ERR_INTERNAL"}

        if result.get("ok"):
            self._record_success()
        return result

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            return resp.status_code == 200 and resp.json().get("ok") is True
        except Exception:
            return False

    def _record_failure(self):
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

    def _record_success(self):
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_pc_agent.py -v
```

Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add executor/pc_agent.py tests/test_pc_agent.py
git commit -m "feat(executor): add PCAgentExecutor with tenacity retry + responses tests"
```

---

### Task 1.4: 业务侧调度器（带降级）

**Files:**
- Create: `executor/dispatcher.py`
- Test: `tests/test_dispatcher.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_dispatcher.py`：
```python
import pytest
from executor.dispatcher import ExecutorDispatcher
from executor.base import Intent, IntentType
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor


def test_dispatcher_routes_pc_intent_to_pc_agent():
    """显示器/音量/应用/B 站 走 pc_agent"""
    pc = PCAgentExecutor("http://pc.local:18770")
    stub = DevStubExecutor()
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub)

    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert target is pc

    target = disp._route(IntentType.LAUNCH_APP)
    assert target is pc

    target = disp._route(IntentType.BILIBILI_SEARCH)
    assert target is pc


def test_dispatcher_routes_local_intent_to_stub():
    """本机屏意图走 stub（本期 dev_stub，本机实现在 Plan 2）"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub)

    target = disp._route(IntentType.ADJUST_LOCAL_BACKLIGHT)
    assert target is stub


def test_dispatcher_falls_back_to_stub_when_pc_unhealthy():
    """PC 连续失败 N 次后，所有意图走 stub（降级）"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, fail_threshold=3)

    # 模拟 PC 失败
    pc._record_failure()
    pc._record_failure()
    pc._record_failure()

    # PC 意图也走 stub
    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert target is stub


def test_dispatcher_recovers_after_pc_health_check():
    """健康检查通过后恢复走 PC"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, fail_threshold=2, health_check_interval=0)

    pc._record_failure()
    pc._record_failure()

    # 模拟健康检查成功
    disp._last_health_check = 0
    disp._health_check_ok = True

    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert target is pc
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_dispatcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'executor.dispatcher'`

- [ ] **Step 3: 实现 Dispatcher**

写入 `executor/dispatcher.py`：
```python
"""Executor 调度器 — 决定每个意图走 pc_agent 还是 dev_stub
支持 PC 失败降级：连续 N 次失败后，所有 PC 意图降级到 stub（仅 dev 用）
"""
from __future__ import annotations
import time
from typing import Optional
from executor.base import Executor, Intent, IntentType
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor


# 走 PC agent 的意图（PC 侧功能）
_PC_INTENTS = {
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP,
    IntentType.SET_INPUT, IntentType.LIST_INPUTS,
    IntentType.SET_VOLUME, IntentType.ADJUST_VOLUME,
    IntentType.LAUNCH_APP, IntentType.CLOSE_APP, IntentType.FOCUS_APP, IntentType.LIST_APPS,
    IntentType.BILIBILI_SEARCH,
}

# 走本地（stub，本期 Plan 2 替换为真实实现）
_LOCAL_INTENTS = {
    IntentType.SET_LOCAL_BACKLIGHT, IntentType.ADJUST_LOCAL_BACKLIGHT,
}


class ExecutorDispatcher:
    """意图→执行器 调度器

    使用方式：
        disp = ExecutorDispatcher(pc_agent=PCAgentExecutor(...), dev_stub=DevStubExecutor())
        result = disp.dispatch(intent)
    """

    def __init__(self, pc_agent: PCAgentExecutor, dev_stub: DevStubExecutor,
                 fail_threshold: int = 3, health_check_interval: float = 30.0):
        self.pc_agent = pc_agent
        self.dev_stub = dev_stub
        self.fail_threshold = fail_threshold
        self.health_check_interval = health_check_interval
        self._last_health_check: float = 0.0
        self._health_check_ok: bool = True

    def dispatch(self, intent: Intent) -> dict:
        """派发意图到对应执行器"""
        exe = self._route(intent)
        return exe.execute_safe(intent)

    def _route(self, intent_type: IntentType) -> Executor:
        """根据意图类型 + PC 健康状态选择执行器"""
        if intent_type in _LOCAL_INTENTS:
            return self.dev_stub  # 本期 stub；Plan 2 替换为 LocalExecutor

        # PC 意图：检查 PC 是否健康
        if self._is_pc_healthy():
            return self.pc_agent
        else:
            return self.dev_stub  # 降级

    def _is_pc_healthy(self) -> bool:
        """PC 健康判定：连续失败 < 阈值 才算健康；否则 30s 心跳探测一次"""
        if self.pc_agent.consecutive_failures < self.fail_threshold:
            return True

        # 超过阈值，限速心跳
        now = time.time()
        if now - self._last_health_check < self.health_check_interval:
            return False  # 还没到探测时间，继续走 stub

        # 探测
        self._last_health_check = now
        self._health_check_ok = self.pc_agent.health_check()
        if self._health_check_ok:
            # 健康了，清零失败计数
            self.pc_agent._record_success()
        return self._health_check_ok
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_dispatcher.py -v
```

Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add executor/dispatcher.py tests/test_dispatcher.py
git commit -m "feat(executor): add ExecutorDispatcher with PC health + fallback"
```

---

## Phase 2: server.py 改造（删 Win32 / 加 /native）

### Task 2.1: 删除 DDC-CI / WMI 路由

**Files:**
- Modify: `server.py` (删除 DDC-CI / WMI / bilibili / sensevoice 路由)
- Test: `tests/test_server.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_server.py`：
```python
"""测试 server.py 路由表。BaseHTTPRequestHandler 紧耦合 socket，改为测纯函数。"""
import json
import sys
import importlib


def test_server_module_imports():
    """server.py 能被 import（无语法错误）"""
    import server  # noqa: F401


def test_health_endpoint_defined_in_do_get():
    """do_GET 中应包含 /health 分支（先失败再补）"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/health" in src, "do_GET 中找不到 /health 分支"


def test_ddcci_route_removed_from_do_get():
    """do_GET 中应不再包含 /ddcci 分支"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/ddcci/" not in src, "do_GET 仍包含 /ddcci/，应删除"


def test_bilibili_route_removed():
    """do_GET 中应不再包含 /bilibili 分支"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/bilibili/" not in src, "do_GET 仍包含 /bilibili/，应删除"


def test_powershell_subprocess_removed():
    """server.py 中不应再有 'powershell' 调用"""
    import server
    import inspect
    src = inspect.getsource(server)
    assert "powershell" not in src.lower(), "server.py 仍含 PowerShell 调用"
```

- [ ] **Step 2: 备份 server.py 并删除 Windows 专有代码**

打开 `server.py`，删除以下方法体（保留类结构）：
- `_handle_ddcci()` 整个方法
- `_handle_i2c()` 整个方法
- `_handle_native()` 中调 PowerShell / WMI 的部分（GET / POST 内的 `subprocess.run(["powershell", ...])`）
- `_handle_bilibili()` 整个方法（移到 win_agent/）
- `_handle_sensevoice()` 整个方法（Plan 3 NPU ASR 替换）
- 删 `import ctypes` 块、`import ctypes.wintypes` 块
- 删 `subprocess.run(["powershell", ...])` 调用

具体删除锚点（grep 后用 Edit 删）：

```bash
# 1. 找 DDC-CI 入口
grep -n "def _handle_ddcci\|def _handle_i2c\|def _handle_bilibili\|def _handle_sensevoice\|def _handle_native" server.py
```

按 grep 输出的行号定位，每个 `def ...` 到下一个 `def ...` 之间的内容整段删除（保留一个 `pass` 或合并到下一个方法）。

- [ ] **Step 3: 在 do_GET / do_POST 中移除对已删路由的引用**

具体锚点：
```python
# 删除这些分支
elif self.path.startswith("/i2c/"): self._handle_i2c()
elif self.path.startswith("/ddcci/"): self._handle_ddcci("GET")
elif self.path.startswith("/bilibili/"): self._handle_bilibili()
```

- [ ] **Step 4: 添加 /health 路由**

在 `do_GET` 中第一个分支（`/exit` 之前）插入：
```python
        if self.path.startswith("/health"):
            self._send_json(200, {"ok": True, "version": "0.2.0-linux", "platform": "linux-aarch64"})
            return
```

- [ ] **Step 5: 启动 server 自检**

```bash
python server.py &
sleep 1
curl -s http://127.0.0.1:18766/health
kill %1
```

Expected:
```json
{"ok": true, "version": "0.2.0-linux", "platform": "linux-aarch64"}
```

- [ ] **Step 6: 提交**

```bash
git add server.py
git commit -m "refactor(server): remove DDC-CI / WMI / bilibili / sensevoice routes; add /health"
```

---

### Task 2.2: 新增 /native 路由（本机屏软调）

**Files:**
- Modify: `server.py` (新增 `_handle_native` 简化版，只调本机屏)
- Test: `tests/test_server.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_server.py`：
```python
def test_native_endpoint_in_do_get():
    """do_GET 中应处理 /native 前缀"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/native/" in src, "do_GET 中应处理 /native/ 前缀"


def test_handle_native_method_exists():
    """Handler 应该有 _handle_native 方法"""
    import server
    assert hasattr(server.Handler, "_handle_native"), "缺少 _handle_native 方法"


def test_handle_native_backlight_get_returns_50_stub():
    """_handle_native 调 GET /native/backlight 应返回 50 stub"""
    import server
    import inspect
    src = inspect.getsource(server.Handler._handle_native)
    assert "/backlight" in src, "_handle_native 应处理 backlight"
    assert "50" in src, "Plan 1 stub 应返回 50"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_server.py -v
```

Expected: 测试本身可能通过（因为 Handler 一直存在）；这 task 主要是为下一步做铺垫。

- [ ] **Step 3: 实现 _handle_native 简化版**

在 `server.py` 中**替换**原 `_handle_native` 方法。**Plan 1 阶段先 stub**（让接口可调），**Plan 2 用 linux/backlight.py 真实实现**：

```python
    def _handle_native(self, method):
        """本机屏幕软调（Plan 1 stub，Plan 2 替换为 linux/backlight.py）"""
        path = self.path.split("?")[0]
        endpoint = path.replace("/native/", "", 1).strip("/")

        if endpoint == "backlight" and method == "GET":
            # Plan 1 stub
            self._send_json(200, {"ok": True, "data": {"value": 50, "note": "stub; Plan 2 用 /sys/class/backlight"}})
        elif endpoint == "backlight" and method == "POST":
            body = self._read_json()
            value = body.get("value", 50)
            self._send_json(200, {"ok": True, "data": {"value": max(0, min(100, value)), "note": "stub"}})
        elif endpoint == "ping":
            self._send_json(200, {"ok": True, "data": {"pong": True}})
        else:
            self._send_json(404, {"ok": False, "err": f"unknown native endpoint: {endpoint}"})
```

- [ ] **Step 4: 启动 server 验证**

```bash
python server.py &
sleep 1
curl -s http://127.0.0.1:18766/native/backlight
curl -s -X POST -H "Content-Type: application/json" -d '{"value":80}' http://127.0.0.1:18766/native/backlight
curl -s http://127.0.0.1:18766/native/ping
kill %1
```

Expected:
```json
{"ok": true, "data": {"value": 50, "note": "stub; Plan 2 用 /sys/class/backlight"}}
{"ok": true, "data": {"value": 80, "note": "stub"}}
{"ok": true, "data": {"pong": true}}
```

- [ ] **Step 5: 提交**

```bash
git add server.py tests/test_server.py
git commit -m "feat(server): add /native route stub for backlight/ping"
```

---

### Task 2.3: 删除 .bat 启动脚本依赖

**Files:**
- Modify: `start-widget.bat` (保留兼容，但 README 提示用 .sh)
- Create: `start-widget.sh`

- [ ] **Step 1: 写 start-widget.sh**

写入 `start-widget.sh`：
```bash
#!/bin/bash
# RK3576 (Ubuntu 22.04 aarch64) 启动脚本
set -e

cd "$(dirname "$0")"

# 预检
if [ -f scripts/check_arm64.sh ]; then
    bash scripts/check_arm64.sh
fi

# 激活 venv
if [ -d .venv ]; then
    source .venv/bin/activate
fi

# 关旧进程
pkill -f "python.*widget.py" 2>/dev/null || true
sleep 0.5

# 启动
exec python widget.py
```

- [ ] **Step 2: 加执行权限并提交**

```bash
chmod +x start-widget.sh
git add start-widget.sh
git commit -m "feat(port): add start-widget.sh for Linux/AArch64"
```

---

## Phase 3: 一键跑全测脚本

### Task 3.1: run_all_arm64.sh

**Files:**
- Create: `scripts/run_all_arm64.sh`

- [ ] **Step 1: 写脚本**

写入 `scripts/run_all_arm64.sh`：
```bash
#!/bin/bash
# 板子上一键跑全测；CI 失败非零退出。
set -e
cd "$(dirname "$0")/.."

echo "=== 1. 预检 ==="
bash scripts/check_arm64.sh || { echo "预检失败，跳过测试"; exit 1; }

echo
echo "=== 2. 单元 + 集成 ==="
pytest tests/ -v --tb=short

echo
echo "=== 3. Bench ==="
if [ -f tests/bench_arm64.py ]; then
    python tests/bench_arm64.py --output bench_report_$(date +%Y%m%d_%H%M%S).json || echo "bench 跳过（板子才有）"
else
    echo "tests/bench_arm64.py 不存在（Plan 3 才会建）"
fi

echo
echo "=== 4. E2E 延迟 ==="
if [ -f tests/e2e_latency.sh ]; then
    bash tests/e2e_latency.sh || echo "e2e 跳过"
else
    echo "tests/e2e_latency.sh 不存在（Plan 3 才会建）"
fi

echo
echo "=== 5. 长稳（30 分钟，单独跑）==="
echo "如需跑：python tests/test_stability_arm.py --duration 1800"

echo
echo "[OK] Plan 1 测试全过"
```

- [ ] **Step 2: 提交**

```bash
chmod +x scripts/run_all_arm64.sh
git add scripts/run_all_arm64.sh
git commit -m "feat(port): add run_all_arm64.sh test runner"
```

---

## Phase 4: 文档

### Task 4.1: README 增补 Linux 启动说明

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 README 末尾加 "RK3576 移植" 章节**

追加到 `README.md`：
```markdown
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
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs(port): add RK3576 port section to README"
```

---

## 验收标准（Plan 1 完成时）

- [ ] `pytest tests/ -v` 全过（计划 4 个测试文件，至少 17 个用例）
- [ ] `python server.py` 启动后 `curl /health` 返回 200 + 正确 JSON
- [ ] `python -c "from executor.dispatcher import ExecutorDispatcher; ..."` 能正常 import
- [ ] `python -c "from executor.pc_agent import PCAgentExecutor; e = PCAgentExecutor('http://fake'); print(e.health_check())"` 返回 False（不可达）
- [ ] `bash scripts/check_arm64.sh` 在 x86 上不崩，警告项可接受
- [ ] `git log --oneline` 显示至少 8 个 commit，commit message 规范

## 后续 Plan 入口

- **Plan 2**: `docs/superpowers/plans/2026-06-17-rk3576-port-plan2-linux.md`（待写）
  - `linux/audio_io.py` / `linux/backlight.py` / `linux/display.py`
  - `widget.py` 字体回退 + 删 pycaw
  - `voice_pipeline.py` 切 mic backend + 路由到 dispatcher
  - `start-widget.sh` 端到端冒烟
  - 需要 RK3576 板子

- **Plan 3**: `docs/superpowers/plans/2026-06-17-rk3576-port-plan3-npu-verification.md`（待写）
  - `npu/rknn_asr.py` + SenseVoice-Small → RKNN 模型转换
  - `npu/wakeword.py` + openWakeWord → RKNN
  - `tests/bench_arm64.py` / `tests/e2e_latency.sh` / `tests/test_stability_arm.py`
  - 需要 RK3576 板子 + RKNN 工具链
