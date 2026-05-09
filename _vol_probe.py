"""测试各种读取系统主音量的方案"""
import subprocess
import ctypes
import os
import winreg
import json

print("=" * 60)
print("音量读取方案测试")
print("=" * 60)

# ── 1. nircmd getsysvolume ──
print("\n[1] nircmd.exe getsysvolume:")
nircmd = r"C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\nircmd.exe"
if os.path.exists(nircmd):
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        r = subprocess.run(
            [nircmd, "getsysvolume"],
            capture_output=True, text=True, timeout=5,
            startupinfo=si,
        )
        print(f"  exit={r.returncode} stdout=[{r.stdout}] stderr=[{r.stderr}] len={len(r.stdout)}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  NOT FOUND")

# ── 2. waveOutGetVolume (winmm) ──
print("\n[2] waveOutGetVolume (winmm.dll):")
try:
    v = ctypes.c_uint32()
    ctypes.windll.winmm.waveOutGetVolume(0, ctypes.byref(v))
    lo = v.value & 0xFFFF
    hi = (v.value >> 16) & 0xFFFF
    avg_pct = int((lo + hi) / 2 * 100 / 0xFFFF)
    print(f"  raw=0x{v.value:08X} lo={lo} hi={hi} avg_pct={avg_pct}%")
except Exception as e:
    print(f"  ERROR: {e}")

# ── 3. 注册表搜索 ──
print("\n[3] 注册表中的音量相关值:")
registry_paths = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Multimedia"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Applets\SysTray"),
]
for hkey, subkey in registry_paths:
    try:
        k = winreg.OpenKey(hkey, subkey)
        j = 0
        while True:
            try:
                name, val, typ = winreg.EnumValue(k, j)
                val_str = str(val)[:120]
                if "volume" in name.lower() or "vol" in str(val).lower() or "audio" in name.lower():
                    print(f"  {subkey}/{name} = {val_str}")
                j += 1
            except OSError:
                break
        winreg.CloseKey(k)
    except Exception as e:
        pass

# ── 4. WMI Win32_SoundDevice ──
print("\n[4] WMI Win32_SoundDevice:")
try:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "Get-WmiObject Win32_SoundDevice | Select-Object Name,Status,Volume -First 3 | ConvertTo-Json"],
        capture_output=True, text=True, timeout=10,
    )
    if r.stdout.strip():
        data = json.loads(r.stdout)
        for item in (data if isinstance(data, list) else [data]):
            print(f"  {item.get('Name','?')} vol={item.get('Volume','N/A')}")
    else:
        print(f"  stdout empty, stderr: {r.stderr[:200]}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── 5. PowerShell Audio endpoint via .NET reflection ──
print("\n[5] 尝试通过 Assembly 加载 CoreAudio API:")
try:
    ps_cmd = (
        "try { "
        "[System.Reflection.Assembly]::LoadWithPartialName('CoreAudioApi') | Out-Null; "
        "$devType = [Type]::GetTypeFromCLSID('{BCDE0395-E52F-467C-8E3D-C57293534E89}'); "
        "Write-Host ('devType=' + $devType); "
        "} catch { Write-Host ('ERR: ' + $_.Exception.Message) }"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=10,
    )
    print(f"  {r.stdout.strip() or 'empty'}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── 6. DirectX XAudio2 / WASAPI via ctypes ──
print("\n[6] 尝试通过 ole32 CoCreateInstance 直接调用 IAudioEndpointVolume:")
try:
    import uuid
    IID_IAudioEndpointVolume = uuid.UUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
    CLSID_MMDevEnum = uuid.UUID("{BCDE0395-E52F-467C-8E3D-C57293534E89}")
    IID_IMMDevEnum = uuid.UUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    
    hr = ctypes.windll.ole32.CoInitialize(None)
    
    pDevEnum = ctypes.c_void_p()
    hr = ctypes.windll.ole32.CoCreateInstance(
        bytes.fromhex(CLSID_MMDevEnum.hex.replace('-', '')), None, 1,
        bytes.fromhex(IID_IMMDevEnum.hex.replace('-', '')), ctypes.byref(pDevEnum),
    )
    print(f"  CoCreateInstance MMDeviceEnumerator hr=0x{hr:08X}")
    
    # 如果成功，继续获取默认设备
    if hr == 0 and pDevEnum.value:
        # COM available - would need vtable calls to proceed
        print(f"  Device enumerator created, would need vtable dispatch")
    else:
        print(f"  COM not available (expected on this machine)")
        
    ctypes.windll.ole32.CoUninitialize()
except Exception as e:
    print(f"  ERROR: {e}")

# ── 7. 检查是否有其他音频工具可用 ──
print("\n[7] 其他可用工具:")
tools = ["nircmd", "pactl", "amixer"]
for t in tools:
    try:
        r = subprocess.run(["where", t], capture_output=True, text=True, timeout=3)
        if r.stdout.strip():
            print(f"  {t}: {r.stdout.strip()}")
    except:
        pass

print("\n" + "=" * 60)
print("测试完成")
