"""桌面应用管理 — 扫描已安装应用、启动、关闭、切换"""
import os, subprocess, json, ctypes, ctypes.wintypes, re, time

# ── 缓存 ─────────────────────────────────────────────────────────
_app_cache = {}          # {小写应用名: 完整路径}
_cache_time = 0
_CACHE_TTL = 300         # 缓存 5 分钟

# ── 常见应用别名 ──────────────────────────────────────────────────
_ALIASES = {
    "微信": "wechat", "qq": "qq", "钉钉": "dingtalk", "飞书": "feishu",
    "记事本": "notepad", "画图": "mspaint", "计算器": "calculator",
    "浏览器": "chrome", "谷歌": "chrome", "谷歌浏览器": "chrome",
    "火狐": "firefox", "edge": "msedge", "微软浏览器": "msedge",
    "资源管理器": "explorer", "文件管理器": "explorer",
    "任务管理器": "taskmgr", "控制面板": "control",
    "命令行": "cmd", "终端": "windowsterminal", "powershell": "powershell",
    "vscode": "code", "vs code": "code", "编辑器": "code",
    "网易云": "cloudmusic", "网易云音乐": "cloudmusic",
    "qq音乐": "qqmusic", "酷狗": "kugou",
    "wps": "wps", "word": "winword", "excel": "excel", "ppt": "powerpnt",
    "steam": "steam", "企业微信": "wxwork",
    "微软商店": "ms-windows-store:", "应用商店": "ms-windows-store:", "商店": "ms-windows-store:",
    "回收站": "shell:RecycleBinFolder",
    "outlook": "ms-outlook:", "邮件": "ms-outlook:",
}


def _log(msg):
    try:
        ts = time.strftime("%H:%M:%S")
        print(f"[AppMgr] {ts} {msg}")
    except Exception:
        pass


def _parse_shortcuts():
    """用 PowerShell 解析开始菜单快捷方式，返回 {小写名称: 目标路径}"""
    ps_script = r'''
$dirs = @(
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
    "$env:AppData\Microsoft\Windows\Start Menu\Programs"
)
$shell = New-Object -ComObject WScript.Shell
$result = @{}
foreach ($dir in $dirs) {
    if (Test-Path $dir) {
        Get-ChildItem -Path $dir -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $lnk = $shell.CreateShortcut($_.FullName)
                $target = $lnk.TargetPath
                if ($target -and (Test-Path $target) -and $target -match '\.(exe|msi)$') {
                    $name = $_.BaseName.ToLower()
                    if (-not $result.ContainsKey($name)) {
                        $result[$name] = $target
                    }
                }
            } catch {}
        }
    }
}
$result | ConvertTo-Json -Compress
'''
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            if isinstance(data, dict):
                skip = {"卸载", "uninstall", "remove"}
                return {k.lower(): v for k, v in data.items()
                        if not any(s in k.lower() for s in skip)}
    except Exception as e:
        _log(f"扫描快捷方式失败: {e}")
    return {}


def refresh_apps():
    """刷新已安装应用缓存"""
    global _app_cache, _cache_time
    _app_cache = _parse_shortcuts()
    _cache_time = time.time()
    _log(f"扫描到 {len(_app_cache)} 个应用")
    return _app_cache


def get_apps():
    """获取已安装应用列表（带缓存）"""
    if time.time() - _cache_time > _CACHE_TTL or not _app_cache:
        refresh_apps()
    return _app_cache


def _resolve_name(name):
    """将用户输入的应用名解析为可搜索的小写名称"""
    name_lower = name.lower().strip()
    # 先查别名
    if name_lower in _ALIASES:
        return _ALIASES[name_lower]
    return name_lower


def _find_app(name):
    """在缓存中查找应用，返回 (显示名, 路径) 或 None"""
    apps = get_apps()
    key = _resolve_name(name)

    # 精确匹配
    if key in apps:
        return key, apps[key]

    # 模糊匹配：key 包含在应用名中，或应用名包含 key
    for app_name, path in apps.items():
        if key in app_name or app_name in key:
            return app_name, path

    # 常见可执行文件直接查找
    common_exes = {
        "notepad": "notepad.exe", "calc": "calc.exe", "mspaint": "mspaint.exe",
        "cmd": "cmd.exe", "powershell": "powershell.exe",
        "explorer": "explorer.exe", "taskmgr": "taskmgr.exe",
        "control": "control.exe", "regedit": "regedit.exe",
        "snippingtool": "SnippingTool.exe",
    }
    if key in common_exes:
        return key, common_exes[key]

    return None, None


def launch_app(name):
    """启动应用，返回 (成功, 消息)"""
    resolved = _resolve_name(name)

    # URI 协议（ms-windows-store:）或 shell 命令（shell:RecycleBinFolder）直接打开
    if ":" in resolved and not os.path.isabs(resolved):
        try:
            subprocess.Popen(["cmd", "/c", "start", "", resolved],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
            _log(f"启动URI: {name} -> {resolved}")
            return True, f"已打开{name}"
        except Exception as e:
            return False, f"打开{name}失败：{e}"

    app_name, path = _find_app(name)
    if not path:
        return False, f"未找到应用：{name}"

    try:
        if os.path.isabs(path):
            subprocess.Popen(path, shell=False)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
        _log(f"启动应用: {app_name} -> {path}")
        return True, f"已打开{app_name}"
    except Exception as e:
        _log(f"启动应用失败: {e}")
        return False, f"打开{app_name}失败：{e}"


def close_app(name):
    """关闭应用，返回 (成功, 消息)"""
    app_name, path = _find_app(name)
    if not path and not app_name:
        return False, f"未找到应用：{name}"

    # 从路径提取进程名
    proc_name = os.path.basename(path) if path else f"{_resolve_name(name)}.exe"

    try:
        result = subprocess.run(
            ["taskkill", "/IM", proc_name, "/F"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            _log(f"关闭应用: {proc_name}")
            return True, f"已关闭{app_name or name}"
        else:
            err = result.stderr.strip()
            if "not found" in err.lower() or "找不到" in err:
                return False, f"{app_name or name}未在运行"
            return False, f"关闭失败：{err[:80]}"
    except Exception as e:
        _log(f"关闭应用失败: {e}")
        return False, f"关闭{app_name or name}失败：{e}"


def switch_to_app(name):
    """切换到已运行的应用窗口，返回 (成功, 消息)"""
    app_name, path = _find_app(name)
    proc_name = os.path.basename(path) if path else f"{_resolve_name(name)}.exe"

    try:
        # 用 PowerShell 查找窗口句柄并激活
        ps_script = f'''
$proc = Get-Process | Where-Object {{$_.ProcessName -eq "{os.path.splitext(proc_name)[0]}"}} | Select-Object -First 1
if ($proc -and $proc.MainWindowHandle -ne 0) {{
    Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    public class WinAPI {{
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    }}
"@
    [WinAPI]::ShowWindow($proc.MainWindowHandle, 9)  # SW_RESTORE
    [WinAPI]::SetForegroundWindow($proc.MainWindowHandle)
    Write-Output "OK"
}} else {{
    Write-Output "NOT_FOUND"
}}
'''
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if "OK" in result.stdout:
            _log(f"切换到: {app_name or proc_name}")
            return True, f"已切换到{app_name or name}"
        else:
            return False, f"{app_name or name}未在运行"
    except Exception as e:
        _log(f"切换应用失败: {e}")
        return False, f"切换失败：{e}"


def list_running():
    """返回当前运行的应用进程名列表"""
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        procs = set()
        for line in result.stdout.strip().split("\n"):
            if line.startswith('"'):
                name = line.split('"')[1]
                if name.lower().endswith(".exe"):
                    procs.add(name.lower())
        return sorted(procs)
    except Exception:
        return []


def list_gui_apps():
    """列出有可见窗口的 GUI 应用，返回 [(进程名, 窗口标题)] 列表"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # 获取窗口所属进程 ID
    pid = ctypes.c_ulong()
    results = []
    seen_pids = set()

    def enum_callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        # 过滤系统窗口
        if title in ("Default IME", "MSCTFIME UI", "DDE Server Window",
                      "GDI+ Window", "OleDdeWnd", "CiceroUIWndFrame"):
            return True
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        p = pid.value
        if p in seen_pids:
            return True
        seen_pids.add(p)
        # 获取进程名
        proc_handle = kernel32.OpenProcess(0x1000, False, p)  # PROCESS_QUERY_LIMITED_INFORMATION
        if proc_handle:
            buf_size = 260
            buf = ctypes.create_unicode_buffer(buf_size)
            if kernel32.QueryFullProcessImageNameW(proc_handle, 0, buf, ctypes.byref(ctypes.c_ulong(buf_size))):
                proc_path = buf.value
                proc_name = os.path.basename(proc_path)
            else:
                proc_name = f"PID:{p}"
            kernel32.CloseHandle(proc_handle)
        else:
            proc_name = f"PID:{p}"
        results.append((proc_name, title))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

    # 按进程名去重，保留第一个有标题的
    seen_names = set()
    unique = []
    for name, title in results:
        key = name.lower()
        if key not in seen_names:
            seen_names.add(key)
            unique.append((name, title))
    return unique
