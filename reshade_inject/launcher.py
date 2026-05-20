"""
reshade_inject/launcher.py
纯 Python + ctypes 实现 DLL 注入到游戏进程：
1. 下载 addon64 到游戏目录
2. CreateRemoteThread(LoadLibrary(addon_path)) 注入
3. addon64 被加载 → hook D3D11/Vulkan → 应用 HDR shader

用法：
  python launcher.py find --game eldenring.exe
  python launcher.py inject --pid 1234 --game-dir "C:/Games/EldenRing"
  python launcher.py install --game-dir "C:/Games/EldenRing" --url "https://..." --name "renodx-fromsoft_engine.addon64"
  python launcher.py launch --exe "C:/Games/EldenRing/EldenRing.exe" --game-dir "C:/Games/EldenRing" --url "https://..." --name "renodx-fromsoft_engine.addon64"
"""
import os, sys, ctypes, urllib.request, ssl, shutil, subprocess, time, argparse

kernel32 = ctypes.windll.kernel32

# ── Win32 类型 ──────────────────────────────────────────────────────────────
PVOID       = ctypes.c_void_p
HANDLE      = ctypes.c_void_p
DWORD       = ctypes.c_ulong
SIZE_T      = ctypes.c_size_t
LPVOID      = ctypes.c_void_p
LPCSTR      = ctypes.c_char_p
LPCWSTR     = ctypes.c_wchar_p
BOOL        = ctypes.c_long
PHANDLE     = ctypes.POINTER(HANDLE)
PDWORD      = ctypes.POINTER(DWORD)
PSIZE_T     = ctypes.POINTER(SIZE_T)

# 常量
PAGE_READWRITE  = 0x04
PROCESS_ALL     = 0x1F0FFF
MEM_COMMIT      = 0x1000
MEM_RESERVE     = 0x2000
CREATE_SUSPENDED = 0x00000004
DETACHED_PROCESS = 0x00000008
INFINITE        = 0xFFFFFFFF
WAIT_TIMEOUT    = 0x0102

# ── Win32 API 声明 ─────────────────────────────────────────────────────────

kernel32.OpenProcess.argtypes = [DWORD, BOOL, DWORD]
kernel32.OpenProcess.restype  = HANDLE

kernel32.VirtualAllocEx.argtypes = [HANDLE, LPVOID, SIZE_T, DWORD, DWORD]
kernel32.VirtualAllocEx.restype  = LPVOID

kernel32.VirtualFreeEx.argtypes = [HANDLE, LPVOID, SIZE_T, DWORD]
kernel32.VirtualFreeEx.restype  = BOOL

kernel32.WriteProcessMemory.argtypes = [HANDLE, LPVOID, LPCSTR, SIZE_T, PSIZE_T]
kernel32.WriteProcessMemory.restype  = BOOL

kernel32.ReadProcessMemory.argtypes = [HANDLE, LPVOID, LPVOID, SIZE_T, PSIZE_T]
kernel32.ReadProcessMemory.restype  = BOOL

kernel32.GetProcAddress.argtypes = [HANDLE, LPCSTR]
kernel32.GetProcAddress.restype  = LPVOID

kernel32.GetModuleHandleA.argtypes = [LPCSTR]
kernel32.GetModuleHandleA.restype  = HANDLE

kernel32.CreateRemoteThread.argtypes = [HANDLE, PVOID, SIZE_T, LPVOID, LPVOID, DWORD, PDWORD]
kernel32.CreateRemoteThread.restype  = HANDLE

kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
kernel32.WaitForSingleObject.restype  = DWORD

kernel32.ResumeThread.argtypes = [HANDLE]
kernel32.ResumeThread.restype  = DWORD

kernel32.TerminateProcess.argtypes = [HANDLE, DWORD]
kernel32.TerminateProcess.restype  = BOOL

kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.CloseHandle.restype  = BOOL

kernel32.GetExitCodeThread.argtypes = [HANDLE, PDWORD]
kernel32.GetExitCodeThread.restype  = BOOL

# CreateProcess
kernel32.CreateProcessA.argtypes = [
    LPCSTR, LPCSTR,
    PVOID, PVOID,  # LPSECURITY_ATTRIBUTES
    BOOL, DWORD,   # bInheritHandles, dwCreationFlags
    LPVOID,        # lpEnvironment
    LPCSTR,        # lpCurrentDirectory
    PVOID,         # LPSTARTUPINFOA
    PVOID          # LPPROCESS_INFORMATION
]
kernel32.CreateProcessA.restype = BOOL

kernel32.CreateProcessW.argtypes = [
    LPCWSTR, LPVOID,
    PVOID, PVOID, BOOL, DWORD,
    LPVOID, LPCWSTR,
    PVOID, PVOID
]
kernel32.CreateProcessW.restype = BOOL

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = DWORD

# EnumProcesses
ctypes.windll.psapi.EnumProcesses.argtypes = [ctypes.POINTER(DWORD), DWORD, ctypes.POINTER(DWORD)]
ctypes.windll.psapi.EnumProcesses.restype  = BOOL
psapi = ctypes.windll.psapi
psapi.EnumProcessModules.argtypes = [HANDLE, ctypes.POINTER(HANDLE), DWORD, ctypes.POINTER(DWORD)]
psapi.EnumProcessModules.restype = BOOL
psapi.GetModuleBaseNameA.argtypes = [HANDLE, HANDLE, ctypes.c_char_p, DWORD]
psapi.GetModuleBaseNameA.restype  = DWORD


def log(msg):
    print(f"[reshade] {msg}", flush=True)


# ── 核心注入 ────────────────────────────────────────────────────────────────

def remote_loadlibrary(pid, dll_path):
    """在目标进程执行 LoadLibraryA(dll_path)"""
    # 获取 kernel32 基址和 LoadLibraryA 地址
    h_kernel = kernel32.GetModuleHandleA(b"kernel32.dll")
    if not h_kernel:
        log(f"GetModuleHandleA(kernel32) failed: {kernel32.GetLastError()}")
        return False
    loadlib = kernel32.GetProcAddress(h_kernel, b"LoadLibraryA")
    if not loadlib:
        log(f"GetProcAddress(LoadLibraryA) failed: {kernel32.GetLastError()}")
        return False

    # 打开目标进程
    h_proc = kernel32.OpenProcess(PROCESS_ALL, False, pid)
    if not h_proc:
        log(f"OpenProcess({pid}) failed: {kernel32.GetLastError()}")
        return False

    # 分配内存写入 DLL 路径
    path_bytes = dll_path.encode("utf-8") + b"\x00"
    alloc_addr = kernel32.VirtualAllocEx(
        h_proc, None, len(path_bytes),
        MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
    )
    if not alloc_addr:
        log(f"VirtualAllocEx failed: {kernel32.GetLastError()}")
        kernel32.CloseHandle(h_proc)
        return False

    written = SIZE_T()
    ok = kernel32.WriteProcessMemory(
        h_proc, alloc_addr, path_bytes, len(path_bytes), ctypes.byref(written)
    )
    if not ok or written.value < len(path_bytes):
        log(f"WriteProcessMemory failed: {kernel32.GetLastError()}")
        kernel32.VirtualFreeEx(h_proc, alloc_addr, 0, 0x8000)
        kernel32.CloseHandle(h_proc)
        return False

    # 创建远程线程
    thread_id = DWORD()
    h_thread = kernel32.CreateRemoteThread(
        h_proc, None, 0, loadlib, alloc_addr, 0, ctypes.byref(thread_id)
    )
    if not h_thread:
        log(f"CreateRemoteThread failed: {kernel32.GetLastError()}")
        kernel32.VirtualFreeEx(h_proc, alloc_addr, 0, 0x8000)
        kernel32.CloseHandle(h_proc)
        return False

    # 等待 LoadLibrary 完成
    kernel32.WaitForSingleObject(h_thread, 8000)
    exit_code = DWORD()
    kernel32.GetExitCodeThread(h_thread, ctypes.byref(exit_code))
    kernel32.CloseHandle(h_thread)

    # 检查结果：LoadLibrary 返回模块句柄（非零 = 成功）
    if exit_code.value == 0:
        log(f"LoadLibrary 返回 0，addon 可能加载失败")
    else:
        log(f"Addon 注入成功，模块句柄=0x{exit_code.value:08X}")

    kernel32.VirtualFreeEx(h_proc, alloc_addr, 0, 0x8000)
    kernel32.CloseHandle(h_proc)
    return exit_code.value != 0


# ── 进程操作 ────────────────────────────────────────────────────────────────

def find_process(name):
    """按名称找 PID"""
    name = name.lower()
    if not name.endswith(".exe"):
        name += ".exe"
    pids = (DWORD * 256)()
    n = psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(DWORD()))
    for i in range(n):
        pid = pids[i]
        if pid == 0:
            continue
        h = kernel32.OpenProcess(PROCESS_ALL, False, pid)
        if not h:
            continue
        try:
            modules = (HANDLE * 64)()
            cb = DWORD()
            if psapi.EnumProcessModules(h, modules, ctypes.sizeof(modules), ctypes.byref(cb)):
                buf = ctypes.create_string_buffer(260)
                psapi.GetModuleBaseNameA(h, modules[0], buf, 260)
                base = buf.value.decode("ascii", errors="replace").lower()
                if name in base:
                    kernel32.CloseHandle(h)
                    return pid
        except Exception:
            pass
        kernel32.CloseHandle(h)
    return None


def find_processes(name):
    """返回所有匹配的 (pid, exe_name)"""
    name = name.lower()
    if not name.endswith(".exe"):
        name += ".exe"
    pids = (DWORD * 256)()
    n = psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(DWORD()))
    matches = []
    for i in range(n):
        pid = pids[i]
        if pid == 0:
            continue
        h = kernel32.OpenProcess(PROCESS_ALL, False, pid)
        if not h:
            continue
        try:
            modules = (HANDLE * 64)()
            cb = DWORD()
            if psapi.EnumProcessModules(h, modules, ctypes.sizeof(modules), ctypes.byref(cb)):
                buf = ctypes.create_string_buffer(260)
                psapi.GetModuleBaseNameA(h, modules[0], buf, 260)
                base = buf.value.decode("ascii", errors="replace").lower()
                if name in base:
                    matches.append((pid, base))
        except Exception:
            pass
        kernel32.CloseHandle(h)
    return matches


# ── 启动游戏（挂起 → 注入 → 恢复）───────────────────────────────────────────

def launch_suspended(exe_path, work_dir=None):
    """CreateProcess 创建挂起进程，返回 (h_process, h_thread, pid, tid)"""
    startupinfo = (ctypes.c_ubyte * 68)()
    startupinfo[0] = 68  # cb
    startupinfo[2] = 0x04  # dwFlags = STARTF_USESHOWWINDOW
    startupinfo[3] = 1     # wShowWindow = SW_SHOWNORMAL
    proc_info = (DWORD * 4)()

    CREATE_SUSPENDED = 0x00000004
    DETACHED = 0x00000008

    ok = kernel32.CreateProcessA(
        exe_path.encode("utf-8"), None,
        None, None, False,
        CREATE_SUSPENDED | DETACHED,
        None,
        (work_dir or os.path.dirname(exe_path)).encode("utf-8"),
        startupinfo, proc_info
    )
    if not ok:
        err = kernel32.GetLastError()
        log(f"CreateProcessA failed: {err}")
        return None
    return proc_info[0], proc_info[1], proc_info[2], proc_info[3]  # hProc, hThread, pid, tid


# ── ReshadeInjector 主类 ────────────────────────────────────────────────────

class ReshadeInjector:
    """
    注入流程：
    1. download_addon() → 下载 addon64 到 game_dir
    2. inject(pid)       → 把 addon64 作为 DLL LoadLibrary 到游戏进程
       （addon64 被加载 → DllMain → hook D3D11/Vulkan → 注入 HDR shader）
    3. launch_with_injection() → 挂起启动 → 注入 → 恢复主线程
    """

    def __init__(self, game_dir):
        self.game_dir = game_dir

    def download_addon(self, url, addon_name):
        """下载 addon 到游戏目录"""
        dest = os.path.join(self.game_dir, addon_name)
        if os.path.exists(dest):
            log(f"Addon 已存在: {dest}")
            return True, dest
        os.makedirs(self.game_dir, exist_ok=True)
        log(f"下载 addon: {url}")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            data = urllib.request.urlopen(url, timeout=30, context=ctx).read()
            with open(dest, "wb") as f:
                f.write(data)
            log(f"已保存: {dest} ({len(data) // 1024} KB)")
            return True, dest
        except Exception as e:
            log(f"下载失败: {e}")
            return False, str(e)

    def inject(self, pid, addon_path):
        """
        将 addon64 作为 DLL 注入到已运行的游戏进程。
        addon 被 LoadLibrary 后 hook D3D11 → 注入 HDR shader。
        """
        log(f"注入 PID {pid}: LoadLibrary({addon_path})")
        return remote_loadlibrary(pid, addon_path)

    def launch_with_injection(self, exe_path, addon_url, addon_name):
        """
        启动游戏 + 注入 addon（最可靠方式）。
        进程在主线程挂起时注入 → 恢复后 addon hook 生效。
        """
        # 1. 下载
        ok, result = self.download_addon(addon_url, addon_name)
        if not ok:
            return False, result

        # 2. 启动挂起
        proc_info = launch_suspended(exe_path)
        if not proc_info:
            return False, "CreateProcess 失败"
        h_proc, h_thread, pid, tid = proc_info
        log(f"进程已挂起 (PID={pid})")

        # 3. 注入 addon
        addon_abs = os.path.join(self.game_dir, addon_name)
        ok = self.inject(pid, addon_abs)
        kernel32.ResumeThread(h_thread)
        kernel32.CloseHandle(h_thread)
        kernel32.CloseHandle(h_proc)

        if ok:
            return True, f"游戏启动中，PID={pid}，HDR shader 已注入"
        else:
            return False, f"注入失败（可能被安全软件拦截）"


# ── CLI 入口 ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="ReShade HDR injector")
    sub = p.add_subparsers(dest="cmd")

    find_p = sub.add_parser("find")
    find_p.add_argument("--game", required=True)

    inj_p = sub.add_parser("inject")
    inj_p.add_argument("--pid", type=int, required=True)
    inj_p.add_argument("--game-dir", required=True)
    inj_p.add_argument("--addon-name", required=True)

    dl_p = sub.add_parser("install")
    dl_p.add_argument("--game-dir", required=True)
    dl_p.add_argument("--url", required=True)
    dl_p.add_argument("--name", required=True)

    launch_p = sub.add_parser("launch")
    launch_p.add_argument("--exe", required=True)
    launch_p.add_argument("--game-dir", required=True)
    launch_p.add_argument("--url", required=True)
    launch_p.add_argument("--name", required=True)

    args = p.parse_args()

    if args.cmd == "find":
        matches = find_processes(args.game)
        if matches:
            for pid, name in matches:
                print(f"  PID {pid}: {name}")
        else:
            print("  未找到")

    elif args.cmd == "inject":
        inj = ReshadeInjector(args.game_dir)
        addon_path = os.path.join(args.game_dir, args.addon_name)
        ok = inj.inject(args.pid, addon_path)
        print("成功" if ok else "失败")

    elif args.cmd == "install":
        inj = ReshadeInjector(args.game_dir)
        ok, msg = inj.download_addon(args.url, args.name)
        print(msg)

    elif args.cmd == "launch":
        inj = ReshadeInjector(args.game_dir)
        ok, msg = inj.launch_with_injection(args.exe, args.url, args.name)
        print(msg)


if __name__ == "__main__":
    main()
