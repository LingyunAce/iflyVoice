"""通过 PowerShell .NET Activator 创建 CoreAudio COM 对象读取系统主音量"""
import subprocess
import json
import sys

# 方案A: PowerShell Activator + dynamic DLR (之前已知能创建 ComObject)
ps_script = r'''
try {
    $guid = [System.Guid]::Parse("BCDE0395-E52F-467C-8E3D-C57293534E89")
    $type = [System.Type]::GetTypeFromCLSID($guid)
    $dev = [System.Activator]::CreateInstance($type)
    
    # GetDefaultAudioEndpoint(eRender=0, eConsole=1)
    $speaker = $dev.GetDefaultAudioEndpoint(0, 1)
    $name = $speaker.FriendlyName
    
    # IAudioEndpointVolume.MasterVolumeLevelScalar
    $epVol = $speaker.AudioEndpointVolume
    $scalar = $epVol.MasterVolumeLevelScalar
    $pct = [math]::Round($scalar * 100)
    $mute = $epVol.Mute
    
    # Output as structured JSON
    @{success=$true; volume_pct=$pct; scalar=$scalar; muted=$mute; device=$name} | ConvertTo-Json -Compress
} catch {
    @{success=$false; error=($_.Exception.Message)} | ConvertTo-Json -Compress
}
'''

print("=" * 60)
print("方案A: PS Activator + dynamic → IAudioEndpointVolume")
print("=" * 60)

r = subprocess.run(
    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
    capture_output=True, text=True, timeout=15,
    errors="replace",
)
print(f"exit={r.returncode}")
print(f"stdout: {r.stdout[:500]}")
if r.stderr.strip():
    print(f"stderr: {r.stderr[:300]}")

# 尝试解析结果
try:
    data = json.loads(r.stdout.strip())
    print(f"\n解析结果: {json.dumps(data, indent=2, ensure_ascii=False)}")
except:
    pass


# 方案B: 用 C# 编译一个小 exe（如果 PS 动态方式不行）
print("\n" + "=" * 60)
print("方案B: C# 编译 exe 直接调用 CoreAudio")
print("=" * 60)

csharp_code = r'''
using System;
using System.Runtime.InteropServices;

class VolReader {
    static void Main() {
        try {
            var guid = new Guid("{BCDE0395-E52F-467C-8E3D-C57293534E89}");
            var type = Type.GetTypeFromCLSID(guid);
            dynamic dev = Activator.CreateInstance(type);
            
            // eRender=0, eConsole=1
            dynamic speaker = dev.GetDefaultAudioEndpoint(0, 1);
            string name = speaker.FriendlyName;
            
            dynamic epVol = speaker.AudioEndpointVolume;
            float scalar = epVol.MasterVolumeLevelScalar;
            bool mute = epVol.Mute;
            int pct = (int)Math.Round(scalar * 100);
            
            Console.WriteLine(pct.ToString());
            Console.Error.WriteLine(name);
        } catch (Exception ex) {
            Console.Error.WriteLine(ex.GetType().Name + ":" + ex.Message);
            Console.WriteLine("-1");
        }
    }
}
'''

import os
src = os.path.join(os.path.dirname(__file__ or "."), "_vol_reader.cs")
exe = os.path.join(os.path.dirname(__file__ or "."), "_vol_reader.exe")

with open(src, "w") as f:
    f.write(csharp_code)

# Find csc.exe
csc_candidates = [
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft.NET", "Framework", "v4.0.30319", "csc.exe"),
    os.path.join(os.environ.get("windir", ""), "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe"),
]
csc = None
for c in csc_candidates:
    if os.path.isfile(c):
        csc = csc
        break

if not csc:
    print("csc.exe NOT FOUND - cannot compile C# helper")
else:
    print(f"csc: {csc}")
    r2 = subprocess.run(
        [csc, "/target:exe", "/out:" + exe, "/nologo", src],
        capture_output=True, text=True, timeout=30,
    )
    print(f"编译 exit={r2.returncode}, stderr={r2.stderr[:200]}")
    
    if os.path.exists(exe):
        r3 = subprocess.run([exe], capture_output=True, text=True, timeout=10)
        print(f"\n执行 exit={r3.returncode}")
        print(f"stdout=[{r3.stdout}]")
        print(f"stderr=[{r3.stderr}]")
        
        if r3.stdout.strip().isdigit():
            vol = int(r3.stdout.strip())
            print(f"\n>>> 系统主音量 = {vol}% <<<")
