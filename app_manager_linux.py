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
    """在 /usr/share/applications / ~/.local/share/applications 找 .desktop。
    匹配顺序：精确 > 前缀 > 双向 substring（最后兜底）"""
    name_lower = name.lower().replace(" ", "-")
    dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/snapd/desktop/applications",
    ]
    candidates = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".desktop"):
                continue
            stem = f[:-8].lower()
            full = os.path.join(d, f)
            if stem == name_lower:
                return full  # 精确匹配，立即返回
            if stem.startswith(name_lower):
                candidates.insert(0, (full, stem))  # 前缀匹配优先
            elif name_lower in stem or stem in name_lower:
                candidates.append((full, stem))  # 兜底
    if candidates:
        return candidates[0][0]
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
    """用 pgrep -f 找名字匹配的进程 PID 列表。
    -f 匹配完整命令行，所以 "firefox" 也会匹配 "firefox-bin"、
    "firefox-wrapper.sh" 等。返回去重 PID 列表；找不到返回空 list。
    """
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
    为避免 PID 复用风险，SIGKILL 前用 kill -0 探活。
    返回 {ok, data: {term_sent, kill_sent, pids}} 或 {ok:false, err, code}
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

    term_sent = 0
    for pid in pids:
        try:
            subprocess.run(["kill", "-TERM", str(pid)], check=False, timeout=3)
            term_sent += 1
        except Exception:
            pass
    time.sleep(1)

    # PID 复用防护：只对还活着的发 SIGKILL
    kill_sent = 0
    for pid in pids:
        try:
            probe = subprocess.run(["kill", "-0", str(pid)], check=False, timeout=2)
            if probe.returncode == 0:  # 还活着
                subprocess.run(["kill", "-KILL", str(pid)], check=False, timeout=2)
                kill_sent += 1
        except Exception:
            pass
    return {"ok": True, "data": {"name": name, "term_sent": term_sent,
                                  "kill_sent": kill_sent, "pids": pids}}


def focus_app(name: str) -> dict:
    """切换/聚焦已运行应用的窗口。返回 ok+via 或 ok:false+code"""
    wmctrl = _which("wmctrl")
    if wmctrl:
        try:
            r1 = subprocess.run([wmctrl, "-a", name], check=False,
                                capture_output=True, text=True, timeout=3)
            if r1.returncode == 0:
                return {"ok": True, "data": {"name": name, "via": "wmctrl"}}
            # 窗口未找到
            return {"ok": False, "err": f"wmctrl 未找到匹配 {name!r} 的窗口 (rc={r1.returncode})",
                    "code": "ERR_WINDOW_NOT_FOUND"}
        except Exception as e:
            return {"ok": False, "err": f"wmctrl 失败: {e}", "code": "ERR_FOCUS_FAILED"}

    xdotool = _which("xdotool")
    if xdotool:
        try:
            r2 = subprocess.run([xdotool, "search", "--name", name, "windowactivate"],
                                check=False, capture_output=True, text=True, timeout=3)
            if r2.returncode == 0 and r2.stdout.strip():
                return {"ok": True, "data": {"name": name, "via": "xdotool"}}
            return {"ok": False, "err": f"xdotool 未找到匹配 {name!r} 的窗口",
                    "code": "ERR_WINDOW_NOT_FOUND"}
        except Exception as e:
            return {"ok": False, "err": f"xdotool 失败: {e}", "code": "ERR_FOCUS_FAILED"}

    return {"ok": False, "err": "wmctrl / xdotool 都不可用", "code": "ERR_NO_WINDOW_MANAGER"}


def list_apps() -> dict:
    """列出当前运行的"应用类"进程。返回 {ok, data: [{name, pid}]}
    启发式过滤：跳过 kernel threads、init、已知系统守护进程
    """
    SYSTEM_NAMES = {
        "systemd", "init", "kthreadd", "ksoftirqd", "kworker", "migration",
        "rcu_", "watchdog", "irq", "scsi_", "crypt", "kblockd", "kdevtmpfs",
        "kthrotld", "oom_reaper", "writeback", "kintegrityd", "kswapd0",
        "dbus-daemon", "NetworkManager", "pulseaudio", "Xorg", "wayland-session",
        "systemd-journald", "systemd-udevd", "systemd-logind", "sshd", "cron",
        "polkitd", "snapd", "chronyd", "rsyslogd", "cupsd",
    }
    KERNEL_PREFIXES = ("kworker/", "kthread", "irq/", "scsi_", "ksoftirqd",
                       "migration/", "rcu_", "kblockd", "kdevtmpfs")
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
            # 过滤：pid < 1000（系统进程通常 pid 小）
            if pid < 1000:
                continue
            # 过滤：kernel threads
            if any(name.startswith(p) for p in KERNEL_PREFIXES):
                continue
            # 过滤：已知系统守护进程
            if name in SYSTEM_NAMES:
                continue
            if name in seen:
                continue
            seen.add(name)
            apps.append({"name": name, "pid": pid})
        return {"ok": True, "data": apps}
    except Exception as e:
        return {"ok": False, "err": f"ps 失败: {e}", "code": "ERR_INTERNAL"}