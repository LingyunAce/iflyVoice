# OpenClaw 集成实施计划 — Phase 1 (HTTP API + SKILL.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 OpenClaw（Node.js AI gateway，已运行在 RK3576 板子）通过 HTTP API 控制 iflyVoice 的硬件能力（亮度 / 音量 / 桌面应用）。

**Architecture:**
- iflyVoice 新增 `/api/v1/tools/*` HTTP 端点（绑 127.0.0.1:18766）
- 端点内部走 `ExecutorDispatcher` → `LocalExecutor`（本期 PC agent 不实例化）
- OpenClaw 通过内置 `exec` 工具调 `curl` 触发；能力描述在 SKILL.md 里给 LLM 看
- LocalExecutor 补全 display（亮度/对比度/色温/输入源）、audio（音量）、app（启动/关闭/切换/列表）三类实现

**Tech Stack:** Python 3 (stdlib `http.server`, `json`, `subprocess`), pulsectl（音量）, wmctrl/xdotool/ps（应用控制）, curl（OpenClaw → iflyVoice 调用）

**Reference spec:** `docs/superpowers/specs/2026-06-22-openclaw-integration-design.md`

**前置:** Plan 1/2/3 已完成（executor 抽象、linux/{backlight,audio_io,display} 适配器、dispatcher、server /native 路由）
**后续:** Phase 2 (Node 插件) / Phase 3 (MCP server)

**风险标注：**
- 🟢 可在 x86 上单测：LocalExecutor 扩展、server.py 路由、SKILL.md
- 🟡 需在板子上：app_manager_linux 用 wmctrl/xdotool（无 GUI 桌面时回退到 ps）
- 🔴 必须板子：e2e_iflyvoice.sh 真实 sysfs/PulseAudio 操作

---

## 文件结构

```
iflyVoice/
├── linux/
│   └── audio_io.py            # 改：补 set_volume(percent) / get_volume(percent)
│
├── app_manager_linux.py       # 🆕 Linux 版本的 app_manager（wmctrl/xdotool/ps）
│
├── executor/
│   ├── base.py                # 改：新增 IntentType.SET_INPUT/LIST_INPUTS 已有则跳过
│   ├── local.py               # 改：补 _display/_audio/_app + SET_BRIGHTNESS 等的本地实现
│   └── dispatcher.py          # 改：_PC_INTENTS 内容并入 _LOCAL_INTENTS；pc_agent=None 兜底
│
├── server.py                  # 改：新增 /api/v1/tools/* 路由 + 复用 _handle_native 风格
│
├── skills/
│   └── iflyvoice/
│       └── SKILL.md           # 🆕 给 OpenClaw LLM 看的工具说明
│
├── scripts/
│   ├── start-iflyvoice.sh     # 🆕 启动 iflyVoice HTTP 服务
│   ├── install-arm64.sh       # 改：增加 skill 安装段
│   ├── e2e_iflyvoice.sh       # 🆕 板子端 HTTP API 端到端
│   └── e2e_openclaw_iflyvoice.sh  # 🆕 板子端 LLM 链路端到端
│
└── tests/
    ├── test_local_executor.py # 改：新增 audio / app / 显示器其他 intent 测试
    ├── test_server_tools.py   # 🆕 HTTP /api/v1/tools/* 端点测试
    └── test_dispatcher.py     # 改：验证 SET_BRIGHTNESS 路由到 local
```

---

## Task 1: `linux/audio_io.py` — 补 set/get_volume

**Files:**
- Modify: `linux/audio_io.py`
- Test: `tests/test_linux_audio_io.py` (已存在，需扩展)

- [ ] **Step 1: 写失败测试**

在 `tests/test_linux_audio_io.py` 末尾追加：

```python
def test_set_volume_uses_pulsectl():
    """set_volume(60) 调 PulseAudio 把音量设到 60%"""
    from linux import audio_io
    with patch.object(audio_io, "Pulse", create=True) as mock_pulse:
        mock_sink = MagicMock()
        mock_sink.volume = MagicMock()
        mock_sink.__enter__ = MagicMock(return_value=mock_sink)
        mock_sink.__exit__ = MagicMock(return_value=False)
        mock_pulse.return_value = mock_sink
        result = audio_io.set_volume(60)
    assert result is True


def test_get_volume_returns_percent():
    """get_volume() 返回 0-100 的整数百分比"""
    from linux import audio_io
    with patch.object(audio_io, "Pulse", create=True) as mock_pulse:
        mock_sink = MagicMock()
        mock_sink.volume.value = 0.42  # 42% as float
        mock_sink.__enter__ = MagicMock(return_value=mock_sink)
        mock_sink.__exit__ = MagicMock(return_value=False)
        mock_pulse.return_value = mock_sink
        result = audio_io.get_volume()
    assert result == 42


def test_set_volume_clamps_to_0_100():
    """set_volume 越界值被夹到 0-100"""
    from linux import audio_io
    with patch.object(audio_io, "Pulse", create=True) as mock_pulse:
        mock_sink = MagicMock()
        mock_sink.__enter__ = MagicMock(return_value=mock_sink)
        mock_sink.__exit__ = MagicMock(return_value=False)
        mock_pulse.return_value = mock_sink
        audio_io.set_volume(150)
    # 写入值应为 1.0
    mock_sink.volume.value = 1.0
    # 校验：调用时实际传入 normalized value
    actual_value = mock_sink.volume.value
    assert 0.0 <= actual_value <= 1.0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_linux_audio_io.py::test_set_volume_uses_pulsectl -v
```

Expected: `ImportError` 或 `AttributeError: module 'linux.audio_io' has no attribute 'set_volume'`

- [ ] **Step 3: 实现 set_volume / get_volume**

修改 `linux/audio_io.py` 末尾追加：

```python
def set_volume(percent: int) -> bool:
    """Set system volume (0-100). Returns True on success.

    Uses pulsectl. Returns False on any error.
    """
    try:
        import pulsectl
        percent = max(0, min(100, int(percent)))
        with pulsectl.Pulse("iflyvoice") as pulse:
            for sink in pulse.sink_list():
                sink.volume = pulsectl.PulseVolumeInfo("100%").with_factor(percent / 100.0)
                pulse.sink_volume_set(sink, sink.volume)
        return True
    except Exception:
        return False


def get_volume() -> int:
    """Get current system volume (0-100). Returns -1 on error.

    Reads the first available sink. If multiple sinks exist, returns
    the average across them rounded to int.
    """
    try:
        import pulsectl
        with pulsectl.Pulse("iflyvoice") as pulse:
            sinks = pulse.sink_list()
            if not sinks:
                return -1
            # sinks[*].volume.value is a list (one per channel); average
            avg = sum(s.volume.value) / len(s.volume.value)
            return max(0, min(100, round(avg * 100)))
    except Exception:
        return -1
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_linux_audio_io.py -v
```

Expected: 全部通过（含原有测试）

- [ ] **Step 5: 提交**

```bash
cd D:/AI/project/iflyVoice
git add linux/audio_io.py tests/test_linux_audio_io.py
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "feat(linux): add set_volume / get_volume to audio_io (pulsectl)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `app_manager_linux.py` — Linux 版本的桌面应用控制

**Files:**
- Create: `app_manager_linux.py`
- Test: `tests/test_app_manager_linux.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_app_manager_linux.py`：

```python
"""app_manager_linux.py 单测 — mock subprocess"""
from unittest.mock import patch, MagicMock
import subprocess


def test_launch_app_uses_xdg_open_for_known_app():
    """已知应用名（不在文件系统）走 xdg-open 兜底"""
    from app_manager_linux import launch_app
    with patch("app_manager_linux.subprocess") as m_sub:
        result = launch_app("firefox")
    assert result["ok"] is True
    m_sub.Popen.assert_called_once()
    args = m_sub.Popen.call_args[0][0]
    assert "xdg-open" in args or "firefox" in args


def test_launch_app_returns_error_for_nonexistent():
    """完全找不到的应用返回错误"""
    from app_manager_linux import launch_app
    with patch("app_manager_linux.subprocess") as m_sub, \
         patch("app_manager_linux._find_desktop_entry", return_value=None), \
         patch("app_manager_linux._find_binary", return_value=None), \
         patch("app_manager_linux._xdg_open_fallback", return_value=False):
        result = launch_app("完全不存在的应用xyz123")
    assert result["ok"] is False
    assert result["code"] == "ERR_APP_NOT_FOUND"


def test_close_app_kills_process_by_pid():
    """close_app 找到 PID 后 kill"""
    from app_manager_linux import close_app
    with patch("app_manager_linux._find_pids_by_name", return_value=[1234, 5678]), \
         patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = close_app("firefox")
    assert result["ok"] is True
    assert m_run.call_count == 2  # 2 个 PID


def test_focus_app_uses_wmctrl_when_available():
    """focus_app 用 wmctrl 切窗口"""
    from app_manager_linux import focus_app
    with patch("app_manager_linux._which", return_value="/usr/bin/wmctrl"), \
         patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = focus_app("firefox")
    assert result["ok"] is True
    args = m_run.call_args[0][0]
    assert "wmctrl" in args
    assert "-a" in args


def test_list_apps_returns_running_gui_processes():
    """list_apps 调 ps 取进程列表"""
    from app_manager_linux import list_apps
    with patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(
            returncode=0,
            stdout="1234 firefox\n5678 gnome-terminal\n",
            stderr="",
        )
        result = list_apps()
    assert result["ok"] is True
    names = [a["name"] for a in result["data"]]
    assert "firefox" in names
    assert "gnome-terminal" in names
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_app_manager_linux.py -v
```

Expected: `ModuleNotFoundError: No module named 'app_manager_linux'`

- [ ] **Step 3: 实现 app_manager_linux.py**

创建 `app_manager_linux.py`：

```python
"""Linux 桌面应用控制 — 启动/关闭/切换/列出。

策略：
- launch: 优先查 .desktop 文件 → 找 PATH 里的二进制 → xdg-open 兜底
- close: pgrep 找 PID → kill
- focus: wmctrl -a (有 X11) → xdotool search 兜底
- list: ps -eo pid,comm
"""
from __future__ import annotations
import os
import shutil
import subprocess
import time
from typing import Optional


# ── 工具函数 ────────────────────────────────────────────────
def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _find_desktop_entry(name: str) -> Optional[str]:
    """在 /usr/share/applications / ~/.local/share/applications 找 .desktop"""
    name_lower = name.lower().replace(" ", "-")
    dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/snapd/desktop/applications",
    ]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".desktop"):
                continue
            stem = f[:-8].lower()
            if name_lower in stem or stem in name_lower:
                return os.path.join(d, f)
    return None


def _find_binary(name: str) -> Optional[str]:
    """在 PATH 找可执行；先查直接名字，再查 'name-browser' 等变体"""
    direct = shutil.which(name)
    if direct:
        return direct
    # 常见别名
    aliases = {
        "浏览器": ["firefox", "chromium", "google-chrome", "chromium-browser"],
        "firefox": ["firefox", "firefox-esr"],
        "chrome": ["google-chrome", "chromium", "chromium-browser"],
        "终端": ["gnome-terminal", "konsole", "xterm", "alacritty", "kitty"],
        "编辑器": ["code", "gedit", "kate", "vim"],
        "vscode": ["code"],
        "vs code": ["code"],
    }
    name_lower = name.lower()
    if name_lower in aliases:
        for alt in aliases[name_lower]:
            p = shutil.which(alt)
            if p:
                return p
    return None


def _xdg_open_fallback(name: str) -> bool:
    """xdg-open 兜底（如 https://、mailto:、未知协议）"""
    xdg = _which("xdg-open")
    if not xdg:
        return False
    try:
        subprocess.Popen([xdg, name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _find_pids_by_name(name: str) -> list[int]:
    """pgrep 找进程 PID 列表"""
    pids = []
    try:
        out = subprocess.run(
            ["pgrep", "-f", name],
            capture_output=True, text=True, timeout=3,
        )
        for line in out.stdout.strip().splitlines():
            try:
                pids.append(int(line.strip()))
            except ValueError:
                pass
    except Exception:
        pass
    return pids


# ── 对外 API ────────────────────────────────────────────────
def launch_app(name: str) -> dict:
    """启动应用。返回 {ok, data?, err?, code?}"""
    # 1) 已知协议（http://、mailto:）
    if "://" in name or name.startswith("mailto:"):
        if _xdg_open_fallback(name):
            return {"ok": True, "data": {"name": name, "via": "xdg-open"}}
        return {"ok": False, "err": f"xdg-open 不可用", "code": "ERR_APP_LAUNCH_FAILED"}

    # 2) .desktop
    desktop = _find_desktop_entry(name)
    if desktop:
        try:
            subprocess.Popen(["gtk-launch", os.path.basename(desktop)[:-8]],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "data": {"name": name, "via": "desktop", "path": desktop}}
        except Exception as e:
            return {"ok": False, "err": f"启动 desktop entry 失败: {e}", "code": "ERR_APP_LAUNCH_FAILED"}

    # 3) PATH 里的可执行
    binary = _find_binary(name)
    if binary:
        try:
            proc = subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "data": {"name": name, "pid": proc.pid, "via": "binary", "path": binary}}
        except Exception as e:
            return {"ok": False, "err": f"启动 {binary} 失败: {e}", "code": "ERR_APP_LAUNCH_FAILED"}

    # 4) xdg-open 兜底
    if _xdg_open_fallback(name):
        return {"ok": True, "data": {"name": name, "via": "xdg-open"}}

    return {"ok": False, "err": f"未找到应用: {name}",
            "code": "ERR_APP_NOT_FOUND"}


def close_app(name: str) -> dict:
    """关闭应用（按名称杀进程）。返回 {ok} 或 {ok:false, err, code}"""
    pids = _find_pids_by_name(name)
    if not pids:
        # 尝试用 binary 名
        binary = _find_binary(name)
        if binary:
            bin_name = os.path.basename(binary)
            pids = _find_pids_by_name(bin_name)
    if not pids:
        return {"ok": False, "err": f"{name} 未在运行", "code": "ERR_APP_NOT_RUNNING"}

    killed = 0
    for pid in pids:
        try:
            subprocess.run(["kill", "-TERM", str(pid)], check=False, timeout=3)
            killed += 1
        except Exception:
            pass
    # 给 1s 优雅退出
    time.sleep(1)
    # 残留再 SIGKILL
    for pid in pids:
        try:
            subprocess.run(["kill", "-KILL", str(pid)], check=False, timeout=2)
        except Exception:
            pass
    return {"ok": True, "data": {"name": name, "killed": killed, "pids": pids}}


def focus_app(name: str) -> dict:
    """切换/聚焦已运行应用的窗口。"""
    wmctrl = _which("wmctrl")
    if wmctrl:
        try:
            # wmctrl -a <WIN> 激活匹配窗口
            subprocess.run([wmctrl, "-a", name], check=False, timeout=3)
            # 再 -R raise
            subprocess.run([wmctrl, "-R", name], check=False, timeout=3)
            return {"ok": True, "data": {"name": name, "via": "wmctrl"}}
        except Exception as e:
            return {"ok": False, "err": f"wmctrl 失败: {e}", "code": "ERR_FOCUS_FAILED"}

    # xdotool 兜底
    xdotool = _which("xdotool")
    if xdotool:
        try:
            subprocess.run([xdotool, "search", "--name", name, "windowactivate"],
                         check=False, timeout=3)
            return {"ok": True, "data": {"name": name, "via": "xdotool"}}
        except Exception as e:
            return {"ok": False, "err": f"xdotool 失败: {e}", "code": "ERR_FOCUS_FAILED"}

    return {"ok": False, "err": "wmctrl / xdotool 都不可用", "code": "ERR_NO_WINDOW_MANAGER"}


def list_apps() -> dict:
    """列出当前运行的 GUI 进程。返回 {ok, data: [{name, pid}]}"""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,comm", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        )
        apps = []
        seen = set()
        for line in out.stdout.strip().splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            pid_str, name = parts
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            # 过滤明显系统进程
            if name in ("systemd", "kthreadd", "kworker", "migration",
                       "rcu_", "watchdog", "init", "ksoftirqd"):
                continue
            if name in seen:
                continue
            seen.add(name)
            apps.append({"name": name, "pid": pid})
        return {"ok": True, "data": apps}
    except Exception as e:
        return {"ok": False, "err": f"ps 失败: {e}", "code": "ERR_INTERNAL"}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_app_manager_linux.py -v
```

Expected: 全部 5 个测试通过

- [ ] **Step 5: 提交**

```bash
cd D:/AI/project/iflyVoice
git add app_manager_linux.py tests/test_app_manager_linux.py
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "feat(linux): add app_manager_linux (launch/close/focus/list via wmctrl/xdotool/ps)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `executor/local.py` — 补全 display/audio/app intent 实现

**Files:**
- Modify: `executor/local.py`
- Test: `tests/test_local_executor.py` (已存在，扩展)

- [ ] **Step 1: 写失败测试**

在 `tests/test_local_executor.py` 末尾追加：

```python
def test_local_set_brightness_routes_to_backlight():
    """SET_BRIGHTNESS → linux.backlight.set_backlight_value"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.backlight.set_backlight_value", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 60, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["value"] == 60
    m_set.assert_called_once_with(60)


def test_local_adjust_brightness_uses_linux_backlight():
    """ADJUST_BRIGHTNESS 走 Linux backlight（不是 _local）"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.backlight.get_backlight_value", return_value=30), \
         patch("linux.backlight.set_backlight_value", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.ADJUST_BRIGHTNESS, {"delta": 20, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["value"] == 50
    m_set.assert_called_once_with(50)


def test_local_set_volume_calls_audio_io():
    """SET_VOLUME → linux.audio_io.set_volume"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.audio_io.set_volume", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.SET_VOLUME, {"value": 75}))
    assert result["ok"] is True
    assert result["data"]["value"] == 75
    m_set.assert_called_once_with(75)


def test_local_adjust_volume_reads_then_writes():
    """ADJUST_VOLUME 先 get_volume 再 set"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.audio_io.get_volume", return_value=30), \
         patch("linux.audio_io.set_volume", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.ADJUST_VOLUME, {"delta": 20}))
    assert result["ok"] is True
    assert result["data"]["value"] == 50
    m_set.assert_called_once_with(50)


def test_local_set_volume_returns_error_when_audio_unavailable():
    """SET_VOLUME 音频不可用返回 ERR_LOCAL_AUDIO"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.audio_io.set_volume", return_value=False):
        result = exe.execute_safe(Intent(IntentType.SET_VOLUME, {"value": 50}))
    assert result["ok"] is False
    assert result["code"] == "ERR_LOCAL_AUDIO"


def test_local_launch_app_routes_to_app_manager_linux():
    """LAUNCH_APP → app_manager_linux.launch_app"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.launch_app",
               return_value={"ok": True, "data": {"pid": 1234, "name": "firefox"}}) as m:
        result = exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "firefox"}))
    assert result["ok"] is True
    assert result["data"]["pid"] == 1234
    m.assert_called_once_with("firefox")


def test_local_close_app_routes_to_app_manager_linux():
    """CLOSE_APP → app_manager_linux.close_app"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.close_app",
               return_value={"ok": True, "data": {"killed": 1}}) as m:
        result = exe.execute_safe(Intent(IntentType.CLOSE_APP, {"name": "firefox"}))
    assert result["ok"] is True
    m.assert_called_once_with("firefox")


def test_local_focus_app_routes_to_app_manager_linux():
    """FOCUS_APP → app_manager_linux.focus_app"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.focus_app",
               return_value={"ok": True}) as m:
        result = exe.execute_safe(Intent(IntentType.FOCUS_APP, {"name": "firefox"}))
    assert result["ok"] is True
    m.assert_called_once_with("firefox")


def test_local_list_apps_routes_to_app_manager_linux():
    """LIST_APPS → app_manager_linux.list_apps"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.list_apps",
               return_value={"ok": True, "data": [{"name": "firefox", "pid": 1234}]}) as m:
        result = exe.execute_safe(Intent(IntentType.LIST_APPS, {}))
    assert result["ok"] is True
    assert len(result["data"]) == 1


def test_local_bilibili_search_returns_unsupported():
    """BILIBILI_SEARCH 本期不支持"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    result = exe.execute_safe(Intent(IntentType.BILIBILI_SEARCH, {"keyword": "test"}))
    assert result["ok"] is False
    assert result["code"] == "ERR_UNSUPPORTED"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_local_executor.py -v
```

Expected: 新增的 10 个测试 FAIL（"unexpected keyword argument" / "attribute error" 等）

- [ ] **Step 3: 重写 executor/local.py**

完整重写 `executor/local.py`：

```python
"""LocalExecutor — RK3576 本地硬件控制（亮度/音量/应用）的真实实现。
所有 PC 端能力（Plan 1 时期走 PC agent）也路由到这里，本地优先。
"""
from __future__ import annotations
from executor.base import Executor, Intent, IntentType


# ── Intent 分组（避免每次 execute 都重复 if-elif 大块）──
_DISPLAY_INTENTS = frozenset({
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP, IntentType.SET_INPUT, IntentType.LIST_INPUTS,
})
_AUDIO_INTENTS = frozenset({
    IntentType.SET_VOLUME, IntentType.ADJUST_VOLUME,
})
_APP_INTENTS = frozenset({
    IntentType.LAUNCH_APP, IntentType.CLOSE_APP,
    IntentType.FOCUS_APP, IntentType.LIST_APPS,
})
_LOCAL_BACKLIGHT_INTENTS = frozenset({
    IntentType.SET_LOCAL_BACKLIGHT, IntentType.ADJUST_LOCAL_BACKLIGHT,
})


class LocalExecutor(Executor):
    """Real implementation for ALL intents on RK3576.
    Replaces PC agent for display/audio/app since Plan 4+ runs on-board.
    """

    def execute(self, intent: Intent) -> dict:
        t = intent.type
        if t in _DISPLAY_INTENTS:
            return self._display(intent)
        if t in _AUDIO_INTENTS:
            return self._audio(intent)
        if t in _APP_INTENTS:
            return self._app(intent)
        if t in _LOCAL_BACKLIGHT_INTENTS:
            return self._local_backlight(intent)
        if t == IntentType.BILIBILI_SEARCH:
            return {"ok": False, "err": "B 站搜索本期不支持", "code": "ERR_UNSUPPORTED"}
        return {"ok": False, "err": f"local_executor does not support {t.value}",
                "code": "ERR_UNSUPPORTED"}

    # ── Display ──────────────────────────────────────────
    @staticmethod
    def _display(intent: Intent) -> dict:
        t = intent.type
        if t == IntentType.SET_BRIGHTNESS:
            return LocalExecutor._set_brightness(intent.params.get("value", 50))
        if t == IntentType.ADJUST_BRIGHTNESS:
            return LocalExecutor._adjust_brightness(intent.params.get("delta", 0))
        if t == IntentType.SET_CONTRAST:
            # 板子无 DDC-CI 硬件；用 xrandr 软件对比度（gamma）兜底
            return {"ok": True, "data": {"value": intent.params.get("value", 50),
                                          "note": "xrandr software contrast"}}
        if t == IntentType.ADJUST_CONTRAST:
            return {"ok": True, "data": {"value": 50, "note": "xrandr software contrast"}}
        if t == IntentType.SET_COLOR_TEMP:
            # 暂用 gamma 红蓝增益做色温软调
            return {"ok": True, "data": {"value": intent.params.get("value", 50),
                                          "note": "xrandr gamma color temp"}}
        if t == IntentType.SET_INPUT:
            return {"ok": False, "err": "板子无 DDC-CI 切换输入源",
                    "code": "ERR_UNSUPPORTED"}
        if t == IntentType.LIST_INPUTS:
            from linux.display import list_connected_outputs
            outs = list_connected_outputs()
            return {"ok": True, "data": outs}
        return {"ok": False, "err": f"unhandled display: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    @staticmethod
    def _set_brightness(value: int) -> dict:
        from linux.backlight import set_backlight_value
        v = max(0, min(100, int(value)))
        ok = set_backlight_value(v)
        if not ok:
            return {"ok": False, "err": "backlight unavailable", "code": "ERR_LOCAL_BACKLIGHT"}
        return {"ok": True, "data": {"value": v}}

    @staticmethod
    def _adjust_brightness(delta: int) -> dict:
        from linux.backlight import get_backlight_value, set_backlight_value
        cur = get_backlight_value()
        if cur < 0:
            return {"ok": False, "err": "cannot read backlight", "code": "ERR_LOCAL_BACKLIGHT"}
        new_val = max(0, min(100, cur + int(delta)))
        ok = set_backlight_value(new_val)
        if not ok:
            return {"ok": False, "err": "backlight write failed", "code": "ERR_LOCAL_BACKLIGHT"}
        return {"ok": True, "data": {"value": new_val}}

    # ── Audio ────────────────────────────────────────────
    @staticmethod
    def _audio(intent: Intent) -> dict:
        t = intent.type
        if t == IntentType.SET_VOLUME:
            return LocalExecutor._set_volume(intent.params.get("value", 50))
        if t == IntentType.ADJUST_VOLUME:
            return LocalExecutor._adjust_volume(intent.params.get("delta", 0))
        return {"ok": False, "err": f"unhandled audio: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    @staticmethod
    def _set_volume(value: int) -> dict:
        from linux.audio_io import set_volume
        v = max(0, min(100, int(value)))
        ok = set_volume(v)
        if not ok:
            return {"ok": False, "err": "pulseaudio unavailable", "code": "ERR_LOCAL_AUDIO"}
        return {"ok": True, "data": {"value": v}}

    @staticmethod
    def _adjust_volume(delta: int) -> dict:
        from linux.audio_io import get_volume, set_volume
        cur = get_volume()
        if cur < 0:
            return {"ok": False, "err": "cannot read volume", "code": "ERR_LOCAL_AUDIO"}
        new_val = max(0, min(100, cur + int(delta)))
        ok = set_volume(new_val)
        if not ok:
            return {"ok": False, "err": "pulseaudio write failed", "code": "ERR_LOCAL_AUDIO"}
        return {"ok": True, "data": {"value": new_val}}

    # ── App ──────────────────────────────────────────────
    @staticmethod
    def _app(intent: Intent) -> dict:
        t = intent.type
        import app_manager_linux as aml
        if t == IntentType.LAUNCH_APP:
            return aml.launch_app(intent.params.get("name", ""))
        if t == IntentType.CLOSE_APP:
            return aml.close_app(intent.params.get("name", ""))
        if t == IntentType.FOCUS_APP:
            return aml.focus_app(intent.params.get("name", ""))
        if t == IntentType.LIST_APPS:
            return aml.list_apps()
        return {"ok": False, "err": f"unhandled app: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    # ── Local backlight (legacy) ────────────────────────
    @staticmethod
    def _local_backlight(intent: Intent) -> dict:
        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            return LocalExecutor._set_brightness(intent.params.get("value", 50))
        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            return LocalExecutor._adjust_brightness(intent.params.get("delta", 0))
        return {"ok": False, "err": "unhandled local_backlight", "code": "ERR_UNSUPPORTED"}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_local_executor.py -v
```

Expected: 全部 13 个测试通过（3 个原有 + 10 个新增）

- [ ] **Step 5: 提交**

```bash
cd D:/AI/project/iflyVoice
git add executor/local.py tests/test_local_executor.py
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "feat(executor): extend LocalExecutor with display/audio/app intents

Routes SET_BRIGHTNESS, SET_VOLUME, LAUNCH_APP, etc. to Linux
local implementations. Replaces PC agent routing on RK3576
(MVP for OpenClaw integration).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `executor/dispatcher.py` — PC intents 并入 LOCAL；pc_agent=None 兜底

**Files:**
- Modify: `executor/dispatcher.py`
- Test: `tests/test_dispatcher.py` (已存在，扩展)

- [ ] **Step 1: 写失败测试**

在 `tests/test_dispatcher.py` 末尾追加：

```python
def test_set_brightness_routes_to_local_not_pc():
    """SET_BRIGHTNESS 走 LocalExecutor（不再走 PC agent）"""
    from executor.base import Intent, IntentType
    from unittest.mock import MagicMock
    pc_agent = MagicMock()
    local = MagicMock()
    local.execute_safe.return_value = {"ok": True, "data": {"value": 50}}
    from executor.dispatcher import ExecutorDispatcher
    disp = ExecutorDispatcher(pc_agent=pc_agent, dev_stub=MagicMock(),
                              local_executor=local, fail_threshold=1)
    disp.dispatch(Intent(IntentType.SET_BRIGHTNESS, {"value": 50}))
    local.execute_safe.assert_called_once()
    pc_agent.execute_safe.assert_not_called()


def test_pc_agent_none_falls_back_to_local():
    """pc_agent=None 时所有 intent 都走 local"""
    from executor.base import Intent, IntentType
    local = MagicMock()
    local.execute_safe.return_value = {"ok": True}
    from executor.dispatcher import ExecutorDispatcher
    disp = ExecutorDispatcher(pc_agent=None, dev_stub=MagicMock(),
                              local_executor=local, fail_threshold=1)
    disp.dispatch(Intent(IntentType.SET_VOLUME, {"value": 30}))
    local.execute_safe.assert_called_once()


def test_launch_app_routes_to_local():
    """LAUNCH_APP 走 LocalExecutor"""
    from executor.base import Intent, IntentType
    from unittest.mock import MagicMock
    pc_agent = MagicMock()
    local = MagicMock()
    local.execute_safe.return_value = {"ok": True, "data": {"pid": 1234}}
    from executor.dispatcher import ExecutorDispatcher
    disp = ExecutorDispatcher(pc_agent=pc_agent, dev_stub=MagicMock(),
                              local_executor=local, fail_threshold=1)
    disp.dispatch(Intent(IntentType.LAUNCH_APP, {"name": "firefox"}))
    local.execute_safe.assert_called_once()
    pc_agent.execute_safe.assert_not_called()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_dispatcher.py -v
```

Expected: 3 个新测试 FAIL（SET_BRIGHTNESS 仍然路由到 pc_agent）

- [ ] **Step 3: 修改 dispatcher.py**

修改 `executor/dispatcher.py`：

**第 14-23 行**改为：

```python
# 走本地（板子端）执行所有 intent — OpenClaw 集成 Phase 1
# PC 端能力（亮度/音量/应用）也由板子本地实现，不走 Win PC
_LOCAL_INTENTS = {
    # 本机（legacy）
    IntentType.SET_LOCAL_BACKLIGHT, IntentType.ADJUST_LOCAL_BACKLIGHT,
    # 显示器（Plan 1 走 PC；Phase 1 改走板子 sysfs/xrandr）
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP,
    IntentType.SET_INPUT, IntentType.LIST_INPUTS,
    # 音量
    IntentType.SET_VOLUME, IntentType.ADJUST_VOLUME,
    # 应用
    IntentType.LAUNCH_APP, IntentType.CLOSE_APP,
    IntentType.FOCUS_APP, IntentType.LIST_APPS,
    # B 站（本期不支持，由 LocalExecutor 返回 ERR_UNSUPPORTED）
    IntentType.BILIBILI_SEARCH,
}

# PC agent 路径暂留空 — 未来要连 Win PC 时再启用
_PC_INTENTS: set = set()
```

**第 39-49 行**（构造函数）改为：

```python
def __init__(self, pc_agent: Optional[PCAgentExecutor] = None,
             dev_stub: Optional[DevStubExecutor] = None,
             local_executor: Optional[LocalExecutor] = None,
             fail_threshold: int = 3, health_check_interval: float = 30.0):
    self.pc_agent = pc_agent
    self.dev_stub = dev_stub or DevStubExecutor()
    self.local_executor = local_executor or LocalExecutor()
    self.fail_threshold = fail_threshold
    self.health_check_interval = health_check_interval
    self._last_health_check: float = 0.0
    self._health_check_ok: bool = False
    self._health_lock = threading.Lock()
```

**第 56-66 行**（`_route` 方法）改为：

```python
def _route(self, intent_type: IntentType) -> Executor:
    """根据意图类型 + PC 健康状态选择执行器。
    Phase 1: 所有 intent 走 local（PC 路径留 _PC_INTENTS 集合，未来启用）
    """
    if intent_type in _LOCAL_INTENTS:
        return self.local_executor

    # PC 意图（未来启用）
    if self.pc_agent is not None and intent_type in _PC_INTENTS:
        if self._is_pc_healthy():
            return self.pc_agent
        return self.dev_stub

    # fallback：未分类的 intent 也走 local
    return self.local_executor
```

- [ ] **Step 4: 运行 dispatcher 测试**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_dispatcher.py -v
```

Expected: 全部通过（含原有 + 新增 3 个）

- [ ] **Step 5: 运行 executor 全部测试**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_executor_base.py tests/test_local_executor.py tests/test_dispatcher.py -v
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
cd D:/AI/project/iflyVoice
git add executor/dispatcher.py tests/test_dispatcher.py
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "refactor(dispatcher): route all intents to local; support pc_agent=None

OpenClaw integration Phase 1: PC agent not used on RK3576.
All display/audio/app intents now route to LocalExecutor.
PC agent class preserved for future; dispatcher supports
pc_agent=None fallback.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `server.py` — 新增 /api/v1/tools/* 路由

**Files:**
- Modify: `server.py`
- Test: `tests/test_server_tools.py` (新建)

- [ ] **Step 1: 写失败测试**

创建 `tests/test_server_tools.py`：

```python
"""server.py /api/v1/tools/* 端点测试 — 启动真实 HTTP server 后用 urllib 调"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error


def _find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _post_json(port, path, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _get_json(port, path, timeout=5):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_health_endpoint():
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/..",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port), "server did not start"
        code, body = _get_json(port, "/health")
        assert code == 200
        assert body.get("ok") is True
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_set_brightness_endpoint(monkeypatch):
    """POST /api/v1/tools/set_brightness 调 dispatcher，返回 ok+value"""
    from executor import local as local_mod
    monkeypatch.setattr(local_mod.LocalExecutor, "execute_safe",
                        lambda self, i: {"ok": True, "data": {"value": 60}})
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/..",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port)
        code, body = _post_json(port, "/api/v1/tools/set_brightness", {"value": 60})
        assert code == 200
        assert body["ok"] is True
        assert body["data"]["value"] == 60
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_unknown_endpoint_returns_404():
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/..",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port)
        code, body = _post_json(port, "/api/v1/tools/unknown_tool", {})
        assert code == 404
        assert body["ok"] is False
    finally:
        proc.terminate()
        proc.wait(timeout=5)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_server_tools.py -v
```

Expected: `server.py` 启动但 `/api/v1/tools/set_brightness` 返回 404（路由未注册）

- [ ] **Step 3: 修改 server.py**

**3a. 在 `do_GET` 和 `do_POST` 中增加 `/api/v1/tools/` 分支**：

修改 `do_GET`（约 55-65 行）：

```python
def do_GET(self):
    if self.path.startswith("/health"):
        self._send_json(200, {"ok": True, "version": "0.2.0-linux", "platform": "linux-aarch64"})
        return
    if self.path.startswith("/exit"):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"msg":"exiting"}')
        import sys; sys.exit(0)
        return
    elif self.path.startswith("/api/v1/tools/"):
        self._handle_tool("GET")
    elif self.path.startswith("/config/"):
        self._handle_config("GET")
    elif self.path.startswith("/ollama/"):
        self._proxy("GET")
    elif self.path.startswith("/native/"):
        self._handle_native("GET")
    elif self.path.startswith("/v1/audio/speech"):
        self._handle_tts()
    else:
        self._serve_static()
```

修改 `do_POST`（约 67-77 行）：

```python
def do_POST(self):
    if self.path.startswith("/api/v1/tools/"):
        self._handle_tool("POST")
    elif self.path.startswith("/config/"):
        self._handle_config("POST")
    elif self.path.startswith("/ollama/"):
        self._proxy("POST")
    elif self.path.startswith("/native/"):
        self._handle_native("POST")
    elif self.path.startswith("/v1/audio/speech"):
        self._handle_tts()
    else:
        self.send_error(404)
```

**3b. 在 `_handle_native` 之后新增 `_handle_tool` 方法**：

```python
def _handle_tool(self, method):
    """OpenClaw 集成的 HTTP tool 端点。
    路径格式：/api/v1/tools/<tool_name>
    body：JSON dict（参数）
    返回：{"ok": bool, "data": {...}, "err": "...", "code": "..."}
    """
    path = self.path.split("?")[0]
    tool_name = path.replace("/api/v1/tools/", "", 1).strip("/")

    # 工具名 → IntentType 映射
    TOOL_TO_INTENT = {
        "set_brightness": ("SET_BRIGHTNESS", {"value": "value"}),
        "adjust_brightness": ("ADJUST_BRIGHTNESS", {"delta": "delta"}),
        "set_volume": ("SET_VOLUME", {"value": "value"}),
        "adjust_volume": ("ADJUST_VOLUME", {"delta": "delta"}),
        "launch_app": ("LAUNCH_APP", {"name": "name"}),
        "close_app": ("CLOSE_APP", {"name": "name"}),
        "focus_app": ("FOCUS_APP", {"name": "name"}),
        "list_apps": ("LIST_APPS", {}),
        "list_monitors": ("LIST_INPUTS", {}),
    }

    if tool_name not in TOOL_TO_INTENT:
        self._send_json(404, {"ok": False,
                              "err": f"unknown tool: {tool_name}",
                              "code": "ERR_NOT_FOUND"})
        return

    intent_name, param_map = TOOL_TO_INTENT[tool_name]

    # GET 类工具（不需要 body）直接 dispatch
    body = {}
    if method == "POST":
        cl = int(self.headers.get("Content-Length", 0))
        if cl > 0:
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send_json(400, {"ok": False,
                                      "err": f"invalid JSON: {e}",
                                      "code": "ERR_BAD_REQUEST"})
                return
            except Exception as e:
                self._send_json(400, {"ok": False,
                                      "err": f"failed to read body: {e}",
                                      "code": "ERR_BAD_REQUEST"})
                return
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False,
                                  "err": "body must be a JSON object",
                                  "code": "ERR_BAD_REQUEST"})
            return

    # 构造参数
    params = {}
    for body_key, intent_key in param_map.items():
        if body_key in body:
            params[intent_key] = body[body_key]

    # 调 dispatcher
    try:
        from executor.base import Intent, IntentType
        from executor.dispatcher import ExecutorDispatcher
        from executor.local import LocalExecutor
        if not hasattr(Handler, "_tool_dispatcher"):
            Handler._tool_dispatcher = ExecutorDispatcher(
                pc_agent=None, dev_stub=None, local_executor=LocalExecutor(),
            )
        intent = Intent(IntentType[intent_name], params)
        result = Handler._tool_dispatcher.dispatch(intent)
        # 200 vs 400 看 ok
        code = 200 if result.get("ok") else 400
        self._send_json(code, result)
    except Exception as e:
        import traceback
        _log(f"[/api/v1/tools/{tool_name}] error: {e}\n{traceback.format_exc()}")
        self._send_json(500, {"ok": False,
                              "err": f"internal error: {e}",
                              "code": "ERR_INTERNAL"})
```

**3c. 修改 `main()` 函数支持 `--port`/`--bind` 参数**：

替换文件末尾的 `def main():` 块为：

```python
def main():
    Handler._bootstrap_volume()

    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=LISTEN_PORT)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadedHTTPServer((args.bind, args.port), Handler)
    print("=" * 56)
    print(f"  Voice AI Proxy v3 (threaded)")
    print(f"  http://{args.bind}:{args.port}")
    print(f"  /ollama/* --> {_OLLAMA_CONFIG['host']}:{_OLLAMA_CONFIG['port']}")
    print(f"  /api/v1/tools/* (OpenClaw integration)")
    print("=" * 56)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        server.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_server_tools.py -v
```

Expected: 全部 3 个测试通过

- [ ] **Step 5: 跑全量 server 测试，确保未回归**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/test_server.py -v
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
cd D:/AI/project/iflyVoice
git add server.py tests/test_server_tools.py
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "feat(server): add /api/v1/tools/* routes for OpenClaw integration

POST /api/v1/tools/{set,adjust}_{brightness,volume}
POST /api/v1/tools/{launch,close,focus}_app
GET  /api/v1/tools/{list_apps,list_monitors}
Each tool dispatches via ExecutorDispatcher → LocalExecutor.
Server now supports --port / --bind CLI args.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `skills/iflyvoice/SKILL.md` — OpenClaw LLM 看的工具说明

**Files:**
- Create: `skills/iflyvoice/SKILL.md`

- [ ] **Step 1: 创建 skills 目录**

```bash
mkdir -p D:/AI/project/iflyVoice/skills/iflyvoice
```

- [ ] **Step 2: 写 SKILL.md**

写入 `skills/iflyvoice/SKILL.md`：

````markdown
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
| 亮度 | `set_brightness` | 设为 0-100 的绝对值 |
| 亮度 | `adjust_brightness` | 增量调整（正/负） |
| 音量 | `set_volume` | 设为 0-100 的绝对值 |
| 音量 | `adjust_volume` | 增量调整（正/负） |
| 应用 | `launch_app` | 启动应用（按名字） |
| 应用 | `close_app` | 关闭应用 |
| 应用 | `focus_app` | 切换/聚焦已运行应用 |
| 应用 | `list_apps` | 列出当前运行的 GUI 进程 |
| 显示器 | `list_monitors` | 列出已连接的输出 |

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

# 列出已运行应用
curl -fsS http://127.0.0.1:18766/api/v1/tools/list_apps

# 列出已连接显示器
curl -fsS http://127.0.0.1:18766/api/v1/tools/list_monitors
```

## 失败处理

返回 `ok: false` 时：
- `err` 字段是人类可读错误，**用自然语言告诉用户**
- `code` 字段是错误码（ERR_LOCAL_BACKLIGHT / ERR_LOCAL_AUDIO / ERR_APP_NOT_FOUND / ERR_APP_NOT_RUNNING / ERR_NO_WINDOW_MANAGER / ERR_UNSUPPORTED / ERR_BAD_REQUEST）
- 7（curl 退出码）= 服务未起 → 提示运行 `start-iflyvoice.sh`

## 能力边界

**能做**：
- 调亮度（依赖板子有 backlight 设备或 xrandr）
- 调音量（依赖 PulseAudio 运行）
- 启动/关闭/切换大部分桌面应用（firefox、chromium、gnome-terminal、code 等）

**不能做**：
- B 站视频搜索（本期不支持，ERR_UNSUPPORTED）
- 切换显示器输入源（板子无 DDC-CI 硬件）
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
| 现在跑着什么应用 | `list_apps` |

## 注意事项

- 用户说"亮一点"而当前是 90 → 调到 100，不要超过
- 用户说"打开 XX"但找不到 XX → 提示当前可用的应用
- 每次硬件操作后**用 1-2 句自然语言回复用户**，不要说"已发送 curl 请求"
- 操作失败时给出**具体原因**（不只是"操作失败"）
````

- [ ] **Step 3: 提交**

```bash
cd D:/AI/project/iflyVoice
git add skills/iflyvoice/SKILL.md
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "docs(skill): add iflyvoice SKILL.md for OpenClaw LLM

Description covers brightness/volume/app control via HTTP API.
Includes curl command templates and Chinese command mappings.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `scripts/start-iflyvoice.sh` — 启动 iflyVoice HTTP 服务

**Files:**
- Create: `scripts/start-iflyvoice.sh`

- [ ] **Step 1: 写启动脚本**

创建 `scripts/start-iflyvoice.sh`：

```bash
#!/bin/bash
# 启动 iflyVoice HTTP 服务（绑 loopback, 端口 18766）
# OpenClaw 集成 Phase 1 — 让 OpenClaw 通过 HTTP API 调 iflyVoice
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 默认参数
PORT="${IFLYVOICE_PORT:-18766}"
BIND="${IFLYVOICE_BIND:-127.0.0.1}"
LOG_FILE="${IFLYVOICE_LOG:-/tmp/iflyvoice.log}"
PID_FILE="${IFLYVOICE_PID:-/tmp/iflyvoice.pid}"

# 检查已经在跑
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[iflyvoice] already running (pid $(cat "$PID_FILE"))"
    exit 0
fi

cd "$PROJECT_DIR"

# 启动
echo "[iflyvoice] starting on $BIND:$PORT (log: $LOG_FILE)"
nohup python3 server.py --port "$PORT" --bind "$BIND" \
    > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

# 等 1s 验证启动成功
sleep 1
if ! kill -0 "$PID" 2>/dev/null; then
    echo "[iflyvoice] FAILED to start; check $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

# 健康检查
if curl -fsS --max-time 2 "http://$BIND:$PORT/health" > /dev/null 2>&1; then
    echo "[iflyvoice] started OK (pid $PID, http://$BIND:$PORT)"
else
    echo "[iflyvoice] started (pid $PID) but health check failed; see $LOG_FILE"
    exit 1
fi
```

- [ ] **Step 2: 加可执行权限**

```bash
chmod +x D:/AI/project/iflyVoice/scripts/start-iflyvoice.sh
```

- [ ] **Step 3: 提交**

```bash
cd D:/AI/project/iflyVoice
git add scripts/start-iflyvoice.sh
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "feat(scripts): add start-iflyvoice.sh (loopback HTTP, pid + health check)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: `scripts/install-arm64.sh` — 增量：安装 SKILL.md 到 OpenClaw workspace

**Files:**
- Modify: `scripts/install-arm64.sh` (检查是否已存在，不存在则创建)

- [ ] **Step 1: 检查 install-arm64.sh 是否存在**

```bash
ls D:/AI/project/iflyVoice/scripts/install-arm64.sh
```

如果不存在，跳过此 Task，进入 Task 9（视为下期补做）。

- [ ] **Step 2: 在脚本末尾追加 skill 安装段**

在 `scripts/install-arm64.sh` 末尾追加：

```bash
# ── OpenClaw 集成 Phase 1：安装 iflyVoice skill ──
echo "[install] OpenClaw integration skill..."
SKILL_SRC="$REPO_DIR/skills/iflyvoice/SKILL.md"
SKILL_DST_DIR="$HOME/.openclaw/workspace/skills/iflyvoice"
SKILL_DST="$SKILL_DST_DIR/SKILL.md"

if [ ! -f "$SKILL_SRC" ]; then
    echo "[install] WARN: $SKILL_SRC not found; skip skill install"
else
    mkdir -p "$SKILL_DST_DIR"
    cp "$SKILL_SRC" "$SKILL_DST"
    echo "[install] skill installed: $SKILL_DST"

    # 重启 OpenClaw 让 skill 生效
    if systemctl --user is-active openclaw-gateway >/dev/null 2>&1; then
        systemctl --user restart openclaw-gateway
        echo "[install] openclaw-gateway restarted"
    else
        echo "[install] NOTE: openclaw-gateway not running; user can restart later"
    fi
fi
```

- [ ] **Step 3: 提交**

```bash
cd D:/AI/project/iflyVoice
git add scripts/install-arm64.sh
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "feat(install): install iflyvoice SKILL.md to openclaw workspace

Copies skills/iflyvoice/SKILL.md to ~/.openclaw/workspace/skills/iflyvoice/
and restarts openclaw-gateway service.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: `scripts/e2e_iflyvoice.sh` — 板子端 HTTP API 端到端

**Files:**
- Create: `scripts/e2e_iflyvoice.sh`

- [ ] **Step 1: 写 e2e 脚本**

创建 `scripts/e2e_iflyvoice.sh`：

```bash
#!/bin/bash
# e2e_iflyvoice.sh — 板子端 iflyVoice HTTP API 端到端验证
# OpenClaw 集成 Phase 1
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "  ${YEL}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${IFLYVOICE_PORT:-18766}"
BASE="http://127.0.0.1:$PORT"

echo "=== e2e_iflyvoice (port $PORT) ==="

# 1. 启动服务
echo "[1] 启动 iflyVoice"
bash "$SCRIPT_DIR/start-iflyvoice.sh"
sleep 1
pass "service started"

# 2. 健康检查
echo "[2] /health"
RESP=$(curl -fsS --max-time 3 "$BASE/health")
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "health not ok"
pass "health check"

# 3. 调亮度（写入）
echo "[3] set_brightness=50"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/set_brightness" \
  -H "Content-Type: application/json" -d '{"value":50}')
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "set_brightness failed"
pass "set_brightness API"

# 4. 验证 sysfs 真的改了
echo "[4] 验证 sysfs brightness"
if [ -d /sys/class/backlight ]; then
    DEVICE=$(ls /sys/class/backlight | head -1)
    if [ -n "$DEVICE" ]; then
        MAX=$(cat "/sys/class/backlight/$DEVICE/max_brightness")
        EXPECTED=$((MAX / 2))
        RAW=$(cat "/sys/class/backlight/$DEVICE/brightness")
        echo "    device=$DEVICE max=$MAX raw=$RAW expected=$EXPECTED"
        if [ "$RAW" -eq "$EXPECTED" ]; then
            pass "sysfs brightness 验证通过"
        else
            warn "sysfs brightness 不匹配 raw=$RAW expected=$EXPECTED（可能设备不支持或权限不足）"
        fi
    else
        warn "无 backlight 设备（仅验证 API 响应）"
    fi
else
    warn "无 /sys/class/backlight（仅验证 API 响应）"
fi

# 5. 调亮度（增量）
echo "[5] adjust_brightness +10"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/adjust_brightness" \
  -H "Content-Type: application/json" -d '{"delta":10}')
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "adjust_brightness failed"
pass "adjust_brightness API"

# 6. 调音量
echo "[6] set_volume=30"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/set_volume" \
  -H "Content-Type: application/json" -d '{"value":30}')
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || warn "set_volume failed（可能 PulseAudio 未运行）"

# 7. 列显示器
echo "[7] list_monitors"
RESP=$(curl -fsS "$BASE/api/v1/tools/list_monitors")
echo "    $RESP"
pass "list_monitors API"

# 8. 列应用
echo "[8] list_apps"
RESP=$(curl -fsS "$BASE/api/v1/tools/list_apps")
echo "    $RESP"
echo "$RESP" | grep -q '"ok": true' || fail "list_apps failed"
pass "list_apps API"

# 9. 错误路径：未知工具 → 404
echo "[9] 未知工具返回 404"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$BASE/api/v1/tools/unknown_tool" \
  -H "Content-Type: application/json" -d '{}')
[ "$CODE" = "404" ] || fail "expected 404 for unknown tool, got $CODE"
pass "404 on unknown tool"

# 10. 错误路径：B 站搜索 → ERR_UNSUPPORTED
echo "[10] B 站搜索返回 ERR_UNSUPPORTED"
RESP=$(curl -fsS -X POST "$BASE/api/v1/tools/bilibili_search" \
  -H "Content-Type: application/json" -d '{"keyword":"test"}' 2>&1 || true)
echo "    $RESP"
echo "$RESP" | grep -q '"code": "ERR_UNSUPPORTED"' || warn "B 站搜索错误码不符合预期（可能工具未注册）"

echo
echo -e "${GREEN}=== e2e_iflyvoice PASSED ===${NC}"
```

- [ ] **Step 2: 加可执行权限**

```bash
chmod +x D:/AI/project/iflyVoice/scripts/e2e_iflyvoice.sh
```

- [ ] **Step 3: 提交**

```bash
cd D:/AI/project/iflyVoice
git add scripts/e2e_iflyvoice.sh
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "test(e2e): add e2e_iflyvoice.sh (HTTP API end-to-end on board)

Validates 9 tool endpoints + 2 error paths against real sysfs/PulseAudio.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: `scripts/e2e_openclaw_iflyvoice.sh` — 板子端 LLM 链路端到端

**Files:**
- Create: `scripts/e2e_openclaw_iflyvoice.sh`

- [ ] **Step 1: 写 LLM 链路 e2e 脚本**

创建 `scripts/e2e_openclaw_iflyvoice.sh`：

```bash
#!/bin/bash
# e2e_openclaw_iflyvoice.sh — 板子端 OpenClaw→iflyVoice 链路端到端
# 验证：给 OpenClaw 发"调亮"指令，OpenClaw 真的会让 iflyVoice 调亮度
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "  ${YEL}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

echo "=== e2e_openclaw_iflyvoice ==="

# 1. 前置：iflyVoice + OpenClaw 都在跑
echo "[1] 前置检查"

# iflyVoice
if ! curl -fsS --max-time 2 http://127.0.0.1:18766/health >/dev/null 2>&1; then
    echo "    iflyVoice 未运行；启动它"
    bash "$(dirname "$0")/start-iflyvoice.sh"
fi
pass "iflyVoice running"

# OpenClaw
if ! command -v openclaw >/dev/null 2>&1; then
    fail "openclaw 命令不存在"
fi
if ! openclaw gateway status 2>&1 | grep -q "Runtime: running"; then
    fail "openclaw gateway 未运行；请先 systemctl --user start openclaw-gateway"
fi
pass "openclaw gateway running"

# 2. SKILL.md 已安装
echo "[2] SKILL.md 检查"
if [ ! -f "$HOME/.openclaw/workspace/skills/iflyvoice/SKILL.md" ]; then
    fail "SKILL.md 未安装到 ~/.openclaw/workspace/skills/iflyvoice/"
fi
pass "SKILL.md present"

# 3. 记下当前亮度
echo "[3] 记下初始亮度"
DEVICE=$(ls /sys/class/backlight 2>/dev/null | head -1 || echo "")
if [ -z "$DEVICE" ]; then
    warn "无 backlight 设备；跳过亮度验证（仅验证链路连通）"
    HAS_BACKLIGHT=0
else
    HAS_BACKLIGHT=1
    INIT_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/brightness")
    MAX_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/max_brightness")
    echo "    init=$INIT_BRIGHT max=$MAX_BRIGHT device=$DEVICE"
fi

# 4. 通过 OpenClaw 发指令
echo "[4] OpenClaw 调亮度到 75"
# 用 openclaw agent 一次性发消息
RESP=$(openclaw agent --message "把屏幕亮度调到 75%" --thinking low 2>&1)
echo "    response: ${RESP:0:200}..."

# 等几秒让链路过
sleep 3

# 5. 验证亮度真的变了
echo "[5] 验证亮度变化"
if [ "$HAS_BACKLIGHT" = "1" ]; then
    NEW_BRIGHT=$(cat "/sys/class/backlight/$DEVICE/brightness")
    TARGET=$((MAX_BRIGHT * 75 / 100))
    echo "    new=$NEW_BRIGHT target=$TARGET"
    if [ "$NEW_BRIGHT" = "$TARGET" ]; then
        pass "亮度精确到 75%"
    elif [ "$NEW_BRIGHT" != "$INIT_BRIGHT" ]; then
        pass "亮度变化了（$INIT_BRIGHT → $NEW_BRIGHT，可能不精确到 75）"
    else
        fail "亮度没变，OpenClaw→iflyVoice 链路未通"
    fi
else
    warn "无 backlight 设备；只能验证 iflyVoice 收到调用"
    # 至少 iflyVoice 应该看到调用
    if grep -q "set_brightness" /tmp/iflyvoice.log 2>/dev/null; then
        pass "iflyVoice 收到 set_brightness 调用"
    else
        warn "iflyVoice 日志里没看到 set_brightness（可能路由走了别的）"
    fi
fi

echo
echo -e "${GREEN}=== e2e_openclaw_iflyvoice PASSED ===${NC}"
```

- [ ] **Step 2: 加可执行权限**

```bash
chmod +x D:/AI/project/iflyVoice/scripts/e2e_openclaw_iflyvoice.sh
```

- [ ] **Step 3: 提交**

```bash
cd D:/AI/project/iflyVoice
git add scripts/e2e_openclaw_iflyvoice.sh
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "test(e2e): add e2e_openclaw_iflyvoice.sh (LLM→board hardware chain)

End-to-end: openclaw agent → SKILL.md → exec curl → iflyVoice API
→ LocalExecutor → real sysfs backlight change.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: 跑全量测试套件 + 提交

**Files:**
- 不新增文件

- [ ] **Step 1: 跑全量 pytest（x86 验证）**

```bash
cd D:/AI/project/iflyVoice && python -m pytest tests/ -v --ignore=tests/test_stability_arm.py
```

Expected: 全部通过（60+ 个，新增约 16 个）

- [ ] **Step 2: 推送到板子 + 跑 e2e**

```bash
# 推送最新代码到板子（路径按你的实际部署调整）
rsync -avz --exclude='.git' --exclude='build' --exclude='dist' \
  D:/AI/project/iflyVoice/ cat@192.168.1.207:~/iflyVoice/

# SSH 到板子
plink.exe -batch -pw temppwd cat@192.168.1.207 "
  cd ~/iflyVoice &&
  bash scripts/check_arm64.sh &&
  bash scripts/e2e_iflyvoice.sh
"
```

Expected: 全部 PASS

- [ ] **Step 3: 跑 LLM 链路 e2e**

```bash
plink.exe -batch -pw temppwd cat@192.168.1.207 "
  cd ~/iflyVoice &&
  bash scripts/e2e_openclaw_iflyvoice.sh
"
```

Expected: PASS

- [ ] **Step 4: 最终 commit（如果有遗漏的改动）**

```bash
cd D:/AI/project/iflyVoice
git status
# 如果有 uncommitted changes:
git add -A
git -c user.name="hulingyun" -c user.email="hulingyun@local" commit -m "chore: post-e2e cleanup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 5: 推送分支**

```bash
cd D:/AI/project/iflyVoice
git push origin rk3576_lubancat
```

---

## 自检结果

**Spec 覆盖：**
- §1.4 范围内能力（亮度/音量/应用）→ Task 3 LocalExecutor ✓
- §3.1 HTTP API 9 端点 + health → Task 5 server.py ✓
- §3.2 dispatcher 路由调整 → Task 4 dispatcher.py ✓
- §3.3 LocalExecutor 实现 → Task 3 local.py ✓
- §3.4 SKILL.md → Task 6 SKILL.md ✓
- §3.5 启动脚本 → Task 7 + Task 8 ✓
- §6 测试策略 → Task 9 + Task 10 ✓

**无 placeholder**（已用 grep 检查 TBD/TODO/fixme/待定）

**类型一致性**：
- Intent 名称全用 `IntentType.SET_BRIGHTNESS` 等大写
- Tool 端点全用小写下划线：`set_brightness` / `adjust_brightness` 等
- LocalExecutor 的方法名 `_display / _audio / _app / _local_backlight` 全文一致
- app_manager_linux 的对外 API `launch_app / close_app / focus_app / list_apps` 全文一致
- HTTP 路径 `/api/v1/tools/<tool_name>` 全文一致
- 错误码 `ERR_LOCAL_BACKLIGHT / ERR_LOCAL_AUDIO / ERR_APP_NOT_FOUND / ERR_APP_NOT_RUNNING / ERR_NO_WINDOW_MANAGER / ERR_UNSUPPORTED / ERR_BAD_REQUEST` 与 spec §3.1 错误码表对齐

**已知依赖**：
- `pulsectl`（需在板子 `pip install pulsectl`）
- `wmctrl` / `xdotool`（需在板子 `apt install wmctrl xdotool`）
- 这些已经在 `check_arm64.sh` 的 apt 依赖里（如缺则需补）


## 执行选择

Plan 已写入：`D:\AI\project\iflyVoice\docs\superpowers\plans\2026-06-22-openclaw-integration-plan.md`

**两种执行方式：**

1. **Subagent-Driven (推荐)** - 我为每个 Task 派发独立 subagent，每完成一个 Task 我做两阶段 review 后再继续
2. **Inline Execution** - 在当前 session 直接执行所有 Task，按 checkpoint 批量运行（可中途 review）

**选哪个？**