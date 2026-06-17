# RK3576 Port — Plan 2: Linux 用户面移植

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 iflyVoice 的运行时层移植到 RK3576 / Linux aarch64 — mic / 扬声器 / 显示器控制 / 字体 / 进程管理 全部走 Linux 等价物，业务层接 ExecutorDispatcher。

**Architecture:**
- 新建 `linux/` 子模块：`audio_io` (mic+speaker), `backlight` (sysfs/xrandr), `display` (xrandr/wlr-randr)
- 删 `voice_pipeline.py` 的 pycaw + 调 `/ddcci/*` 的硬编码 HTTP（路由已断）
- 业务侧改走 `ExecutorDispatcher`（已存在，Plan 1）
- 新建 `executor/local.py` 实现 LOCAL intent（不是 stub 了）
- widget.py 字体回退 + taskkill → pkill

**Tech Stack:** sounddevice, pulsectl / pyalsaaudio, xrandr, sysfs, subprocess

**Reference spec:** `docs/superpowers/specs/2026-06-17-rk3576-port-design.md` §3 / §4 / §6

**前置：** Plan 1 已完成（executor 抽象、dispatcher、server /native stub、tests 41/41 通过）
**后续：** Plan 3（NPU 接入 + ARM 验证门禁）

**风险标注：**
- 🟢 可在 x86 上单测：`linux/backlight` (mock sysfs)、`executor/local` (mock linux 模块)、字体回退
- 🟡 部分在板子上：mic/speaker 实测、PulseAudio 路径
- 🔴 必须板子：end-to-end smoke

---

## 文件结构（Plan 2 涉及）

```
iflyVoice/
├── linux/                     # 🆕 新增
│   ├── __init__.py
│   ├── audio_io.py            # mic + 扬声器包装
│   ├── backlight.py           # /sys/class/backlight + xrandr
│   └── display.py             # xrandr / wlr-randr
│
├── executor/                  # 扩展
│   ├── local.py               # 🆕 LocalExecutor：真实 LOCAL 实现（替代 dev_stub 兜底）
│   └── dispatcher.py          # 改：路由 LOCAL 改走 LocalExecutor（不总是 dev_stub）
│
├── server.py                  # 改：_handle_native 用 linux/backlight.py 替换 stub
├── voice_pipeline.py          # 大改：pycaw→pulsectl、taskkill→pkill、/ddcci/*→dispatcher
├── widget.py                  # 改：字体回退、taskkill→pkill、删 pycaw
│
├── tests/
│   ├── test_linux_backlight.py    # 🆕
│   ├── test_linux_audio_io.py     # 🆕（仅测试纯函数；硬件相关靠 smoke）
│   ├── test_linux_display.py      # 🆕
│   ├── test_local_executor.py     # 🆕
│   ├── test_voice_pipeline_routing.py  # 🆕 验证 voice_pipeline 调 dispatcher 而非 /ddcci/*
│   └── test_widget_fonts.py       # 🆕 验证字体回退
│
└── scripts/
    └── e2e_smoke.sh           # 🆕 板子端到端 smoke
```

---

## Phase 1: Linux 适配层（可在 x86 上写代码，板子上跑）

### Task 1.1: `linux/backlight.py` — sysfs + xrandr

**Files:**
- Create: `linux/__init__.py`
- Create: `linux/backlight.py`
- Test: `tests/test_linux_backlight.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_linux_backlight.py`：
```python
"""linux/backlight.py 单测 — 用 mock 替代真实 sysfs/xrandr"""
import pytest
from unittest.mock import patch, mock_open, MagicMock


def test_get_backlight_value_reads_sysfs():
    """读取 /sys/class/backlight/*/brightness 当前值"""
    from linux.backlight import get_backlight_value
    fake_content = "75\n"
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=fake_content)):
        val = get_backlight_value()
    assert val == 75


def test_set_backlight_value_writes_sysfs():
    """写 /sys/class/backlight/*/brightness 0~100"""
    from linux.backlight import set_backlight_value
    m_open = mock_open()
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", m_open):
        set_backlight_value(50)
    # 验证写入了 50\n
    handle = m_open()
    handle.write.assert_called_once_with("50\n")


def test_set_backlight_clamps_to_0_100():
    """out-of-range 应当被 clamp"""
    from linux.backlight import set_backlight_value
    m_open = mock_open()
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", m_open):
        set_backlight_value(150)  # 应当 clamp 到 100
    handle = m_open()
    handle.write.assert_called_once_with("100\n")
    set_backlight_value(-10)  # 应当 clamp 到 0
    handle.write.assert_called_with("0\n")


def test_falls_back_to_xrandr_when_sysfs_missing():
    """/sys/class/backlight 不存在时降级到 xrandr --brightness"""
    from linux.backlight import set_backlight_value
    with patch("os.path.exists", return_value=False), \
         patch("subprocess.run") as m_run:
        set_backlight_value(50)
    m_run.assert_called_once()
    args = m_run.call_args[0][0]
    assert "xrandr" in args
    assert "--brightness" in args
    # 50 / 100 = 0.5
    assert "0.5" in args
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_linux_backlight.py -v
```

Expected: `ModuleNotFoundError: No module named 'linux'`

- [ ] **Step 3: 实现 `linux/backlight.py`**

写入 `linux/__init__.py`：
```python
"""Linux 适配层 — audio_io / backlight / display"""
```

写入 `linux/backlight.py`：
```python
"""屏幕背光控制（sysfs 优先，xrandr 兜底）"""
from __future__ import annotations
import os
import subprocess
from typing import Optional

BACKLIGHT_BASE = "/sys/class/backlight"
SYSFS_NAME = "brightness"          # 当前值
SYSFS_MAX = "max_brightness"       # 上限（不一定等于 100）
BRIGHTNESS_FILE = f"{BACKLIGHT_BASE}/{{device}}/{SYSFS_NAME}"


def _find_backlight_device() -> Optional[str]:
    """找到第一个 backlight 设备名（如 'amdgpu_bl0'），没有就返回 None"""
    if not os.path.isdir(BACKLIGHT_BASE):
        return None
    for name in os.listdir(BACKLIGHT_BASE):
        return name  # 取第一个
    return None


def get_backlight_value() -> int:
    """读当前背光（0~100）。失败返回 -1。"""
    device = _find_backlight_device()
    if not device:
        return _xrandr_get_brightness()
    try:
        with open(f"{BACKLIGHT_BASE}/{device}/{SYSFS_NAME}", "r") as f:
            raw = int(f.read().strip())
        max_raw = _get_max_brightness(device)
        return round(raw / max_raw * 100) if max_raw else raw
    except Exception:
        return -1


def set_backlight_value(value: int) -> bool:
    """设背光（0~100，clamp）。返回是否成功。"""
    value = max(0, min(100, int(value)))
    device = _find_backlight_device()
    if device:
        try:
            max_raw = _get_max_brightness(device)
            raw = round(value / 100 * max_raw) if max_raw else value
            with open(f"{BACKLIGHT_BASE}/{device}/{SYSFS_NAME}", "w") as f:
                f.write(f"{raw}\n")
            return True
        except (PermissionError, OSError):
            pass  # 降级到 xrandr
    return _xrandr_set_brightness(value)


def _get_max_brightness(device: str) -> int:
    try:
        with open(f"{BACKLIGHT_BASE}/{device}/{SYSFS_MAX}", "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _xrandr_get_brightness() -> int:
    """xrandr 兜底读"""
    try:
        out = subprocess.run(
            ["xrandr", "--query", "--verbose"],
            capture_output=True, text=True, timeout=2,
        )
        # 找第一个 Brightness: X 字段
        for line in out.stdout.splitlines():
            if "Brightness:" in line:
                return round(float(line.split("Brightness:")[1].strip()) * 100)
    except Exception:
        pass
    return -1


def _xrandr_set_brightness(value: int) -> bool:
    """xrandr 兜底写"""
    factor = value / 100
    try:
        # 取当前活动输出
        out = subprocess.run(
            ["xrandr", "--listactivemonitors"],
            capture_output=True, text=True, timeout=2,
        )
        # 简单粗暴：xrandr --output <name> --brightness <factor>
        # 第一个 monitor 名
        # 解析略复杂，这里用 --brightness 应用到所有输出
        subprocess.run(
            ["xrandr", "--output", "HDMI-1", "--brightness", str(factor)],
            capture_output=True, timeout=2,
        )
        return True
    except Exception:
        return False
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_linux_backlight.py -v
```

Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add linux/ tests/test_linux_backlight.py
git commit -m "feat(linux): add backlight adapter (sysfs + xrandr fallback)"
```

---

### Task 1.2: `linux/audio_io.py` — mic + 扬声器接口

**Files:**
- Create: `linux/audio_io.py`
- Test: `tests/test_linux_audio_io.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_linux_audio_io.py`：
```python
"""linux/audio_io.py 单测 — 测纯函数（设备枚举、配置解析）"""
import pytest
from unittest.mock import patch, MagicMock


def test_list_input_devices_filters_keyword():
    """列出含 'usb' 的输入设备"""
    from linux.audio_io import list_input_devices
    fake_devices = [
        {"name": "USB Microphone", "max_input_channels": 1, "index": 0},
        {"name": "HDA Intel PCH", "max_input_channels": 2, "index": 1},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        result = list_input_devices(keyword="usb")
    assert len(result) == 1
    assert "USB" in result[0]["name"]


def test_list_output_devices_filters_keyword():
    """列出含 'hdmi' 的输出设备"""
    from linux.audio_io import list_output_devices
    fake_devices = [
        {"name": "HDMI Audio Output", "max_output_channels": 2, "index": 5},
        {"name": "Speaker", "max_output_channels": 2, "index": 6},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        result = list_output_devices(keyword="hdmi")
    assert len(result) == 1
    assert "HDMI" in result[0]["name"]


def test_get_default_input_device():
    """返回默认输入设备"""
    from linux.audio_io import get_default_input_device
    fake = {"name": "Default Mic", "index": 0, "max_input_channels": 1}
    with patch("sounddevice.query_devices", return_value=fake):
        dev = get_default_input_device()
    assert dev["name"] == "Default Mic"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_linux_audio_io.py -v
```

Expected: `ModuleNotFoundError: No module named 'linux.audio_io'`

- [ ] **Step 3: 实现 `linux/audio_io.py`**

写入 `linux/audio_io.py`：
```python
"""音频输入/输出 — sounddevice 包装，支持 USB/HDA/HDMI 设备过滤"""
from __future__ import annotations
from typing import Optional
import sounddevice as sd


def list_input_devices(keyword: Optional[str] = None) -> list[dict]:
    """列输入设备（含 max_input_channels > 0 的）。可按 keyword 过滤。"""
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) <= 0:
            continue
        item = {"index": idx, **dev}
        if keyword is None or keyword.lower() in dev["name"].lower():
            result.append(item)
    return result


def list_output_devices(keyword: Optional[str] = None) -> list[dict]:
    """列输出设备"""
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        if dev.get("max_output_channels", 0) <= 0:
            continue
        item = {"index": idx, **dev}
        if keyword is None or keyword.lower() in dev["name"].lower():
            result.append(item)
    return result


def get_default_input_device() -> Optional[dict]:
    """默认输入设备"""
    try:
        idx = sd.default.device[0]
        if idx < 0:
            return None
        dev = sd.query_devices(idx)
        return {"index": idx, **dev}
    except Exception:
        return None


def get_default_output_device() -> Optional[dict]:
    """默认输出设备"""
    try:
        idx = sd.default.device[1]
        if idx < 0:
            return None
        dev = sd.query_devices(idx)
        return {"index": idx, **dev}
    except Exception:
        return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_linux_audio_io.py -v
```

Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add linux/audio_io.py tests/test_linux_audio_io.py
git commit -m "feat(linux): add audio_io adapter (input/output device listing)"
```

---

### Task 1.3: `linux/display.py` — xrandr 包装

**Files:**
- Create: `linux/display.py`
- Test: `tests/test_linux_display.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_linux_display.py`：
```python
"""linux/display.py 单测 — xrandr 解析"""
import pytest
from unittest.mock import patch


SAMPLE_XRANDR = """\
Screen 0: minimum 320 x 200, current 1920 x 1080, maximum 16384 x 16384
HDMI-1 connected 1920x1080+0+0 (normal left inverted right x axis y axis) 600mm x 340mm
   1920x1080     60.00*+  50.00
DP-1 disconnected (normal left inverted right x axis y axis)
"""


def test_list_connected_outputs():
    """列出所有 connected 输出"""
    from linux.display import list_connected_outputs
    with patch("subprocess.run") as m_run:
        m_run.return_value = MagicMock(stdout=SAMPLE_XRANDR, returncode=0)
        outputs = list_connected_outputs()
    assert "HDMI-1" in outputs
    assert "DP-1" not in outputs  # disconnected


def test_get_current_resolution():
    """取当前显示器分辨率"""
    from linux.display import get_current_resolution
    with patch("subprocess.run") as m_run:
        m_run.return_value = MagicMock(stdout=SAMPLE_XRANDR, returncode=0)
        res = get_current_resolution("HDMI-1")
    assert res == (1920, 1080)
```

(用 `MagicMock` 要 import：`from unittest.mock import patch, MagicMock`)

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_linux_display.py -v
```

Expected: `ModuleNotFoundError: No module named 'linux.display'`

- [ ] **Step 3: 实现 `linux/display.py`**

写入 `linux/display.py`：
```python
"""显示输出查询（xrandr 包装）"""
from __future__ import annotations
import re
import subprocess
from typing import Optional


def _run_xrandr() -> str:
    """跑 xrandr --query，返回 stdout（出错时返回空串）"""
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout
    except Exception:
        return ""


def list_connected_outputs() -> list[str]:
    """列出所有 connected 输出（HDMI-1, DP-1, ...）"""
    out = _run_xrandr()
    if not out:
        return []
    pattern = re.compile(r"^(\S+)\s+connected", re.MULTILINE)
    return pattern.findall(out)


def get_current_resolution(output: str) -> Optional[tuple[int, int]]:
    """取指定输出的当前分辨率 (W, H)"""
    out = _run_xrandr()
    if not out:
        return None
    # 找 "OUTPUT connected ... WxH+..." 或 "OUTPUT connected primary WxH+..."
    pattern = re.compile(
        rf"^{re.escape(output)}\s+(?:primary\s+)?connected.*?\b(\d+)x(\d+)\+",
        re.MULTILINE,
    )
    m = pattern.search(out)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_linux_display.py -v
```

Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add linux/display.py tests/test_linux_display.py
git commit -m "feat(linux): add display adapter (xrandr query)"
```

---

### Task 1.4: 替换 server.py `_handle_native` stub 用真 `linux/backlight.py`

**Files:**
- Modify: `server.py` (替换 `_handle_native` 中 backlight 分支)

- [ ] **Step 1: 替换 `_handle_native` 的 backlight 处理**

在 `server.py` 中修改 `_handle_native` 方法（仅 backlight 路径）：

**旧的 GET backlight：**
```python
        if endpoint == "backlight" and method == "GET":
            # Plan 1 stub
            self._send_json(200, {"ok": True, "data": {"value": 50, "note": "stub; Plan 2 用 /sys/class/backlight"}})
```

**新的：**
```python
        if endpoint == "backlight" and method == "GET":
            from linux.backlight import get_backlight_value
            val = get_backlight_value()
            if val < 0:
                self._send_json(503, {"ok": False, "err": "backlight 不可用（无 sysfs 设备且无 xrandr 兜底）", "code": "ERR_BACKLIGHT_UNAVAILABLE"})
            else:
                self._send_json(200, {"ok": True, "data": {"value": val}})
```

**旧的 POST backlight：**
```python
        elif endpoint == "backlight" and method == "POST":
            # ... 读 body / 校验 / clamp / 返回
            self._send_json(200, {"ok": True, "data": {"value": max(0, min(100, value)), "note": "stub"}})
```

**新的：** 在最后一行之前，加一次实际 set：
```python
        elif endpoint == "backlight" and method == "POST":
            # ... (body 解析、校验、int 转换 — 保持 B.5 的健壮路径)
            from linux.backlight import set_backlight_value
            ok = set_backlight_value(value)
            if not ok:
                self._send_json(503, {"ok": False, "err": "backlight 写入失败（权限或无设备）", "code": "ERR_BACKLIGHT_UNAVAILABLE"})
                return
            self._send_json(200, {"ok": True, "data": {"value": max(0, min(100, value))}})
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/ -v
```

Expected: 45 passed (41 from Plan 1 + B + 4 linux/backlight)。在 x86 上 backlight 走 xrandr 兜底，POST 会 503（没真实显示器），但 GET 也 503。**预期测试不会因为新代码崩**。

- [ ] **Step 3: 提交**

```bash
git add server.py
git commit -m "feat(server): wire _handle_native backlight to linux/backlight.py"
```

---

## Phase 2: `executor/local.py` — 真实 LOCAL 实现

### Task 2.1: `executor/local.py` 替代 dev_stub 兜底 LOCAL intent

**Files:**
- Create: `executor/local.py`
- Test: `tests/test_local_executor.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_local_executor.py`：
```python
from unittest.mock import patch
from executor.local import LocalExecutor
from executor.base import Intent, IntentType


def test_local_set_backlight_calls_linux_module():
    """SET_LOCAL_BACKLIGHT 调 linux.backlight.set_backlight_value"""
    exe = LocalExecutor()
    with patch("linux.backlight.set_backlight_value", return_value=True) as m:
        result = exe.execute_safe(Intent(IntentType.SET_LOCAL_BACKLIGHT, {"value": 60}))
    assert result["ok"] is True
    assert result["data"]["value"] == 60
    m.assert_called_once_with(60)


def test_local_adjust_backlight_reads_then_writes():
    """ADJUST_LOCAL_BACKLIGHT 读当前值再调整"""
    exe = LocalExecutor()
    with patch("linux.backlight.get_backlight_value", return_value=30) as m_get, \
         patch("linux.backlight.set_backlight_value", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 20}))
    assert result["ok"] is True
    assert result["data"]["value"] == 50  # 30 + 20
    m_get.assert_called_once()
    m_set.assert_called_once_with(50)


def test_local_returns_503_when_backlight_unavailable():
    """backlight 不可用时返回错误"""
    exe = LocalExecutor()
    with patch("linux.backlight.set_backlight_value", return_value=False):
        result = exe.execute_safe(Intent(IntentType.SET_LOCAL_BACKLIGHT, {"value": 60}))
    assert result["ok"] is False
    assert result["code"] == "ERR_BACKLIGHT_UNAVAILABLE"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_local_executor.py -v
```

Expected: `ModuleNotFoundError: No module named 'executor.local'`

- [ ] **Step 3: 实现 `executor/local.py`**

写入 `executor/local.py`：
```python
"""LocalExecutor — RK3576 本地操作（背光等）的真实实现。
本期只实现 backlight；Plan 3 之后可加 mic_gain / led 等。
"""
from __future__ import annotations
from executor.base import Executor, Intent, IntentType


class LocalExecutor(Executor):
    """本机操作的真实实现。LOCAL intent 路由到这。"""

    def execute(self, intent: Intent) -> dict:
        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            return self._set_backlight(intent.params.get("value", 50))

        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            return self._adjust_backlight(intent.params.get("delta", 0))

        return {"ok": False, "err": f"local_executor 不支持 {intent.type.value}", "code": "ERR_INTERNAL"}

    @staticmethod
    def _set_backlight(value: int) -> dict:
        from linux.backlight import set_backlight_value
        ok = set_backlight_value(value)
        if not ok:
            return {"ok": False, "err": "backlight 不可用", "code": "ERR_BACKLIGHT_UNAVAILABLE"}
        return {"ok": True, "data": {"value": max(0, min(100, int(value)))}}

    @staticmethod
    def _adjust_backlight(delta: int) -> dict:
        from linux.backlight import get_backlight_value, set_backlight_value
        cur = get_backlight_value()
        if cur < 0:
            return {"ok": False, "err": "无法读 backlight", "code": "ERR_BACKLIGHT_UNAVAILABLE"}
        new_val = max(0, min(100, cur + delta))
        ok = set_backlight_value(new_val)
        if not ok:
            return {"ok": False, "err": "backlight 写入失败", "code": "ERR_BACKLIGHT_UNAVAILABLE"}
        return {"ok": True, "data": {"value": new_val}}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_local_executor.py -v
```

Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add executor/local.py tests/test_local_executor.py
git commit -m "feat(executor): add LocalExecutor (real backlight impl, replaces dev_stub fallback)"
```

---

### Task 2.2: 改 `dispatcher.py` — LOCAL 走 `LocalExecutor`，不再总是 dev_stub

**Files:**
- Modify: `executor/dispatcher.py`
- Modify: `tests/test_dispatcher.py`

- [ ] **Step 1: 写新测试**

追加到 `tests/test_dispatcher.py`：

```python
def test_dispatcher_routes_local_to_local_executor(dispatcher, dev_stub):
    """LOCAL 意图走 LocalExecutor，而不是 dev_stub"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    target = dispatcher._route(IntentType.ADJUST_LOCAL_BACKLIGHT)
    assert isinstance(target, LocalExecutor)
    # dev_stub 不应该被调用
    assert target is not dev_stub
```

注意这个测试需要 dispatcher fixture 注入 `local_executor`，所以也要改 conftest.py 和 dispatcher 签名。

- [ ] **Step 2: 改 conftest.py — dispatcher fixture 加 local_executor**

在 `tests/conftest.py` 的 `dispatcher` fixture 改成：

```python
@pytest.fixture
def local_executor():
    from executor.local import LocalExecutor
    return LocalExecutor()


@pytest.fixture
def dispatcher(pc_agent, dev_stub, local_executor):
    from executor.dispatcher import ExecutorDispatcher
    return ExecutorDispatcher(
        pc_agent=pc_agent,
        dev_stub=dev_stub,
        local_executor=local_executor,  # 新增
        fail_threshold=2,
        health_check_interval=0.5,
    )
```

- [ ] **Step 3: 改 dispatcher.py 签名 + 路由**

在 `executor/dispatcher.py`：

**改 import：**
```python
from executor.local import LocalExecutor
```

**改 `__init__`：**
```python
    def __init__(self, pc_agent: PCAgentExecutor, dev_stub: DevStubExecutor,
                 local_executor: LocalExecutor = None,
                 fail_threshold: int = 3, health_check_interval: float = 30.0):
        self.pc_agent = pc_agent
        self.dev_stub = dev_stub
        self.local_executor = local_executor or LocalExecutor()  # 默认实例
        # ... rest unchanged
```

**改 `_route`（LOCAL 走 local_executor，不再走 dev_stub）：**
```python
    def _route(self, intent_type: IntentType) -> Executor:
        if intent_type in _LOCAL_INTENTS:
            return self.local_executor  # ← 改了
        # PC 意图
        if self._is_pc_healthy():
            return self.pc_agent
        else:
            return self.dev_stub  # 降级
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/ -v
```

Expected: 47 passed (45 from 1.4 + 2 new)。

注意：现有 `test_dispatcher_routes_local_intent_to_stub` 测试断言 LOCAL 走 stub，需要更新成断言走 LocalExecutor：

```python
def test_dispatcher_routes_local_intent_to_local_executor(dispatcher, dev_stub):
    """本机屏意图走 LocalExecutor（不总是 dev_stub）"""
    from executor.local import LocalExecutor
    target = dispatcher._route(IntentType.ADJUST_LOCAL_BACKLIGHT)
    assert isinstance(target, LocalExecutor)
    assert target is not dev_stub
```

（在 Task 2.1 已加，新 test 名字应是不同的 — 改名或删旧的 test_dispatcher_routes_local_intent_to_stub）

- [ ] **Step 5: 提交**

```bash
git add executor/dispatcher.py tests/test_dispatcher.py tests/conftest.py
git commit -m "refactor(executor): dispatcher routes LOCAL intents to LocalExecutor"
```

---

## Phase 3: voice_pipeline.py 改造（核心，最复杂）

> ⚠️ 警告：voice_pipeline.py 是 1406 行的运行时核心，本次改造**分小步**做，**每步保持所有现有测试通过**。建议每个子任务后跑 `pytest tests/ -v` + `python -c "import voice_pipeline"` 验证。

### Task 3.1: voice_pipeline.py — 删 pycaw、换 pulsectl

**Files:**
- Modify: `voice_pipeline.py` (line 754-782 附近，音量相关)

- [ ] **Step 1: 替换 pycaw 实现为 pulsectl**

打开 `voice_pipeline.py`，找 `_get_system_volume_obj` 方法（约 754-761 行），替换为：

**旧的：**
```python
    @staticmethod
    def _get_system_volume_obj():
        """获取 pycaw 音量对象（确保 COM 已初始化）"""
        import comtypes
        comtypes.CoInitialize()
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        return speakers.EndpointVolume
```

**新的：**
```python
    @staticmethod
    def _get_system_volume_obj():
        """获取 PulseAudio 音量控制对象（pulsectl）"""
        import pulsectl
        return pulsectl.Pulse("iflyvoice-volume")
```

- [ ] **Step 2: 替换 _get_system_volume / _set_system_volume 内部调用**

把以下方法中所有 `vol.GetMasterVolumeLevelScalar()` 和 `vol.SetMasterVolumeLevelScalar(...)` 调用改为 pulsectl 等价物。

**旧：**
```python
    def _get_system_volume(self):
        try:
            vol = self._get_system_volume_obj()
            return round(vol.GetMasterVolumeLevelScalar() * 100)
        except Exception as e:
            _flog(f"[音量] 读取失败: {e}")
            return None
```

**新：**
```python
    def _get_system_volume(self):
        try:
            pulse = self._get_system_volume_obj()
            for sink in pulse.sink_list():
                if sink.name == "@DEFAULT_SINK@" or sink.index == 0:
                    vol = sink.volume.value_flat
                    pulse.close()
                    return round(vol * 100)
            pulse.close()
            return None
        except Exception as e:
            _flog(f"[音量] 读取失败: {e}")
            return None
```

类似地替换 `_set_system_volume`。

- [ ] **Step 3: 跑测试**

```bash
pytest tests/ -v
python -c "import voice_pipeline; print('import OK')"
```

Expected: pytest 47/47 通过；import 不报错（即使有运行时 pulse 调用，import 阶段不会触发）。

- [ ] **Step 4: 提交**

```bash
git add voice_pipeline.py
git commit -m "fix(pipeline): replace pycaw with pulsectl for Linux volume control"
```

---

### Task 3.2: voice_pipeline.py — taskkill → pkill

**Files:**
- Modify: `voice_pipeline.py` (line 305-320, 1240-1263)
- Modify: `widget.py` (line 656-658, 1601)

- [ ] **Step 1: 替换 voice_pipeline.py 中的 taskkill**

打开 `voice_pipeline.py`：

**找：** line 308-312 附近：
```python
                if self._current_ffplay_proc.poll() is None:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self._current_ffplay_proc.pid)],
                            ...
```

**替换为：**
```python
                if self._current_ffplay_proc.poll() is None:
                    try:
                        subprocess.run(
                            ["pkill", "-TERM", "-P", str(self._current_ffplay_proc.pid)],
                            capture_output=True, timeout=2,
                        )
                        time.sleep(0.2)
                        if self._current_ffplay_proc.poll() is None:
                            self._current_ffplay_proc.kill()
                    except Exception:
                        ...
```

**line 1240-1253 类似替换**（ffplay 中断路径）

- [ ] **Step 2: 替换 widget.py 中的 taskkill**

**line 658 附近：**
```python
            subprocess.run(["taskkill", "/F", "/IM", "ffplay.exe"],
```

**替换为：**
```python
            subprocess.run(["pkill", "-f", "ffplay"],
                           capture_output=True, timeout=2)
```

**line 1601 类似**

- [ ] **Step 3: 跑测试**

```bash
pytest tests/ -v
```

- [ ] **Step 4: 提交**

```bash
git add voice_pipeline.py widget.py
git commit -m "fix(pipeline/widget): taskkill -> pkill for Linux process control"
```

---

### Task 3.3: voice_pipeline.py — 路由走 ExecutorDispatcher（核心改造）

**Files:**
- Modify: `voice_pipeline.py` (主要在 `_execute_display_control` 等方法)
- Create: `tests/test_voice_pipeline_routing.py`

> 这是 Plan 2 最难的改造。**不建议一次性全做**，推荐分 2-3 个 commit：
> - 3.3a: 添加 dispatcher 引用（不改路由逻辑）
> - 3.3b: 把 `/ddcci/*` HTTP 调用改为 dispatcher.dispatch(Intent)
> - 3.3c: 删除 `_http_get_json` / `_http_post_json` 中已无用的部分

- [ ] **Step 1: 3.3a — voice_pipeline 初始化时构造 dispatcher**

在 `__init__` 末尾添加：

```python
        # Plan 2: 业务侧用 ExecutorDispatcher 代替直连 /ddcci/*
        from executor.dispatcher import ExecutorDispatcher
        from executor.dev_stub import DevStubExecutor
        from executor.pc_agent import PCAgentExecutor
        from executor.local import LocalExecutor
        import os as _os

        winpc_url = _os.environ.get("WINPC_AGENT_URL", "http://192.168.1.50:18770")
        self.executor = ExecutorDispatcher(
            pc_agent=PCAgentExecutor(winpc_url, timeout=3.0, max_retries=2),
            dev_stub=DevStubExecutor(),
            local_executor=LocalExecutor(),
        )
```

- [ ] **Step 2: 3.3b — `_execute_display_control` 改用 dispatcher**

打开 `voice_pipeline.py` line 784 附近的 `_execute_display_control` 方法。**核心改动**：把 `self._http_get_json("/ddcci/...")` 改为：

```python
        from executor.base import Intent, IntentType
        intent = Intent(IntentType.LIST_INPUTS, {"monitor_index": 0})
        result = self.executor.dispatch(intent)
        if not result.get("ok"):
            return f"查询输入源失败：{result.get('err', '?')}"
        # ... 解析 result["data"] 而非 r["sources"]
```

类似地，把所有 `self._http_get_json("/ddcci/...")` 和 `self._http_post_json("/ddcci/...", {...})` 改成 `self.executor.dispatch(Intent(...))`。

**重点路径**（必须改）：
- line 747: `_count_monitors` 用 `/ddcci/monitor_count`
- line 792, 815: `/ddcci/input_sources`
- line 830: `/ddcci/input`
- line 933: `/ddcci/status`
- line 939: `/ddcci/contrast_read`
- line 960, 963: `/native/...` → 走 dispatcher 的 LOCAL intent（注意区分 PC 和 LOCAL）

- [ ] **Step 3: 3.3c — 写测试验证 voice_pipeline 不再直连 /ddcci/**

写入 `tests/test_voice_pipeline_routing.py`：

```python
"""验证 voice_pipeline.py 不再直连已删的 /ddcci/* HTTP 端点"""
import inspect


def test_voice_pipeline_no_ddcci_http_calls():
    """voice_pipeline.py 源码不应再有 /ddcci/ HTTP 路径"""
    import voice_pipeline
    src = inspect.getsource(voice_pipeline)
    # 没有 ddcci 路径字符串
    assert "/ddcci/" not in src, "voice_pipeline 仍含 /ddcci/ 路径（已删）"
    assert "taskkill" not in src, "voice_pipeline 仍含 taskkill（Windows）"


def test_voice_pipeline_uses_dispatcher():
    """voice_pipeline 应有 executor 属性（dispatcher）"""
    import voice_pipeline
    # 看类定义里有没有 self.executor 引用
    src = inspect.getsource(voice_pipeline.VoicePipeline)
    assert "self.executor" in src
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/ -v
python -c "import voice_pipeline; print('import OK')"
```

- [ ] **Step 5: 提交**

```bash
git add voice_pipeline.py tests/test_voice_pipeline_routing.py
git commit -m "refactor(pipeline): route all display/app intents via ExecutorDispatcher"
```

---

## Phase 4: widget.py 字体回退

### Task 4.1: widget.py — Microsoft YaHei UI → 字体回退

**Files:**
- Modify: `widget.py` (font references)
- Create: `tests/test_widget_fonts.py`

- [ ] **Step 1: 加字体回退辅助函数**

在 `widget.py` 顶部（imports 之后）加：

```python
def _preferred_font():
    """优先用 Noto Sans CJK；不支持则回退到系统默认 sans-serif"""
    from PySide6.QtGui import QFontDatabase, QFont
    candidates = ["Noto Sans CJK SC", "Noto Sans CJK", "WenQuanYi Micro Hei", "Microsoft YaHei UI"]
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return QFont(name, 10)
    return QFont()  # 系统默认
```

- [ ] **Step 2: 替换 widget.py 中所有硬编码 "Microsoft YaHei UI"**

用 `grep -n "Microsoft YaHei UI" widget.py` 找位置。
推荐：用 Python 脚本批量替换 `"Microsoft YaHei UI"` → `python3 -c "from widget import _preferred_font; print(_preferred_font().family())"` 的结果（运行时才知道），或在所有 setStyleSheet 中改为引用 `_preferred_font().family()`。

**简化方案**：在 widget 启动时统一设置 application 字体：

```python
# 在 QApplication 创建之后、所有 widget 之前：
QApplication.setFont(_preferred_font())
```

这样 setStyleSheet 里的 `font-family:"Microsoft YaHei UI"` 仍存在但被 application 字体覆盖。

- [ ] **Step 3: 写测试**

写入 `tests/test_widget_fonts.py`：

```python
def test_widget_module_imports():
    """widget.py 应能 import（即使 PySide6 在 x86 装了）"""
    # 完整 import 需要 PySide6，先 try
    try:
        import widget
        assert hasattr(widget, "_preferred_font")
    except ImportError as e:
        pytest.skip(f"PySide6 不可用: {e}")


def test_preferred_font_returns_qfont():
    """_preferred_font 应返回 QFont 对象"""
    try:
        from widget import _preferred_font
        from PySide6.QtGui import QFont
        f = _preferred_font()
        assert isinstance(f, QFont)
    except ImportError:
        pytest.skip("PySide6 不可用")
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/test_widget_fonts.py -v
pytest tests/ -v
```

- [ ] **Step 5: 提交**

```bash
git add widget.py tests/test_widget_fonts.py
git commit -m "feat(widget): add Linux font fallback (Noto Sans CJK first)"
```

---

## Phase 5: 端到端 smoke

### Task 5.1: `scripts/e2e_smoke.sh` — 板子端到端 smoke

**Files:**
- Create: `scripts/e2e_smoke.sh`

> 🔴 **此脚本必须在板子上跑**，x86 上部分步骤会失败（mic/camera/HDMI 等）。脚本要支持**分段 pass/fail 报告**。

- [ ] **Step 1: 写脚本**

写入 `scripts/e2e_smoke.sh`：
```bash
#!/bin/bash
# RK3576 端到端 smoke 测试。x86 上部分步骤会失败但脚本不死。
set +e  # 整体不 set -e，让每段单独报告
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; YEL='\033[1;33m'; NC='\033[0m'
pass=0; fail=0; skip=0

check() {
    local name=$1
    local cmd=$2
    echo -n "[$name] "
    if eval "$cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((pass++))
    else
        echo -e "${RED}FAIL${NC}"
        ((fail++))
    fi
}

echo "=== 1. 预检 ==="
check "Python 3.10+" "python3 -c 'import sys; assert sys.version_info >= (3,10)'"
check "PySide6 导入" "python3 -c 'import PySide6'"
check "sounddevice 导入" "python3 -c 'import sounddevice'"
check "onnxruntime 导入" "python3 -c 'import onnxruntime'"

echo
echo "=== 2. pytest ==="
check "全部单测通过" "pytest tests/ -q"

echo
echo "=== 3. 音频设备 ==="
check "列输入设备" "python3 -c 'from linux.audio_io import list_input_devices; list_input_devices()'"
check "列输出设备" "python3 -c 'from linux.audio_io import list_output_devices; list_output_devices()'"

echo
echo "=== 4. server 启动 ==="
python3 server.py >/tmp/voice_server.log 2>&1 &
SERVER_PID=$!
sleep 2
check "GET /health" "curl -sf http://127.0.0.1:18766/health"
check "GET /native/backlight" "curl -sf http://127.0.0.1:18766/native/backlight || true"
kill $SERVER_PID 2>/dev/null

echo
echo "=== 5. 显示器 ==="
check "xrandr 可用" "command -v xrandr"
check "列出 connected 输出" "xrandr --query | grep -q connected"

echo
echo "=== 6. executor 自检 ==="
check "LocalExecutor 构造" "python3 -c 'from executor.local import LocalExecutor; LocalExecutor()'"
check "Dispatcher 构造" "python3 -c 'from executor.dispatcher import ExecutorDispatcher; from executor.dev_stub import DevStubExecutor; from executor.pc_agent import PCAgentExecutor; from executor.local import LocalExecutor; ExecutorDispatcher(PCAgentExecutor(\"http://fake\"), DevStubExecutor(), LocalExecutor())'"

echo
echo "=== 汇总 ==="
echo -e "  ${GREEN}PASS: $pass${NC} | ${RED}FAIL: $fail${NC} | ${YEL}SKIP: $skip${NC}"

[ $fail -eq 0 ] && exit 0 || exit 1
```

- [ ] **Step 2: chmod + 提交**

```bash
chmod +x scripts/e2e_smoke.sh
git add scripts/e2e_smoke.sh
git commit -m "test(port): add e2e_smoke.sh for board end-to-end verification"
```

- [ ] **Step 3: 在板子上跑（不在本机）**

```bash
# 板子上：
bash scripts/e2e_smoke.sh
```

预期：x86 上 fail 多（mic / HDMI / rknn）；板子上大部分 pass。

---

## 验收标准（Plan 2 完成时）

- [ ] x86 上 `pytest tests/ -v` 全部通过（目标 50+ 测试）
- [ ] `python -c "import voice_pipeline, widget, server, executor.local, linux.backlight, linux.audio_io, linux.display"` 不报错
- [ ] Plan 2 期间 8-12 个 commit，commit message 规范
- [ ] server `_handle_native` /native/backlight 在板子上 GET 返回真实背光值
- [ ] widget 在板子上启动不崩，UI 中文显示正常（无方块）
- [ ] 板子上 `bash scripts/e2e_smoke.sh` 大部分 PASS

## 后续 Plan 3 入口

- Plan 3: NPU 接入 + ARM 验证门禁（待写）
  - `npu/rknn_asr.py` + SenseVoice-Small → RKNN 模型转换
  - `npu/wakeword.py` + openWakeWord → RKNN
  - `tests/bench_arm64.py` / `tests/e2e_latency.sh` / `tests/test_stability_arm.py`
  - 需要 RK3576 板子 + RKNN 工具链
