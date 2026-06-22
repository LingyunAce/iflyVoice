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
    """关闭应用（按名称杀进程）。
    策略：先 SIGTERM 让进程优雅退出，1s 后仍存的用 SIGKILL 强制杀。
    返回 {ok} 或 {ok:false, err, code}
    """
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
    time.sleep(1)
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