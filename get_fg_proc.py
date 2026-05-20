"""获取当前前景窗口的进程路径"""
import ctypes, sys
from ctypes import windll

psapi = windll.psapi
kernel32 = windll.kernel32
user32 = windll.user32

GetForegroundWindow = user32.GetForegroundWindow
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
OpenProcess = kernel32.OpenProcess
CloseHandle = kernel32.CloseHandle
GetModuleFileNameExW = psapi.GetModuleFileNameExW
PROCESS_QUERY_INFORMATION = 0x0400

hwnd = GetForegroundWindow()
if not hwnd:
    return None

pid = ctypes.c_ulong()
GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

h = OpenProcess(PROCESS_QUERY_INFORMATION, False, pid.value)
path = None
if h:
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.c_uint(260)
        if GetModuleFileNameExW(h, 0, buf, size):
            path = buf.value
    finally:
        CloseHandle(h)

return path