"""测试 WinRT API 和 Mixer API 读取系统音量"""
import subprocess, os

# ── 方案A: WinRT AudioDeviceController (不依赖 CoreAudio COM) ──
print("=" * 60)
print("方案A: PowerShell WinRT Media.DeviceController")
print("=" * 60)

ps_winrt = r'''
try {
    [Windows.Media.Devices.AudioDeviceController, Windows.Media.Devices, ContentType = WindowsRuntime] | Out-Null
    Write-Host "WinRT loaded OK"
} catch {
    Write-Host "WinRT load ERR: $($_.Exception.Message)"
}

# Try alternative: use System.Management to query WMI for audio info
try {
    $q = "SELECT * FROM Win32_SoundDevice"
    $w = Get-WmiObject -Query $q -ErrorAction Stop
    foreach ($d in $w) {
        Write-Host ("DEV: " + $d.Name + " status=" + $d.Status)
    }
} catch {
    Write-Host ("WMI_ERR: " + $_.Exception.Message)
}
'''

r = subprocess.run(
    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_winrt],
    capture_output=True, text=True, timeout=15,
    errors="replace",
)
print(f"exit={r.returncode}")
out = r.stdout[:600] if r.stdout else "(empty)"
err = r.stderr[:200] if r.stderr else "(empty)"
# Write to file to avoid encoding issues
with open(os.path.join(base_dir, "_vol_probe_out.txt"), "w", encoding="utf-8") as f:
    f.write(f"=== WinRT Test (exit={r.returncode}) ===\nstdout:\n{out}\nstderr:\n{err}\n")
    if os.path.exists(exe):
        f.write(f"\n=== Mixer API Test ===\n")
        f.write(f"exit={r2.returncode} stdout=[{r2.stdout}] stderr=[{r2.stderr}]\n")


# ── 方案B: 简化版 C# Mixer API ──
print("\n" + "=" * 60)
print("方案B: C# Mixer API (简化版)")
print("=" * 60)

csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
base_dir = os.path.dirname(__file__ or ".")
src = os.path.join(base_dir, "_vol_read2.cs")
exe = os.path.join(base_dir, "_vol_read2.exe")

cs_code = '''using System;
using System.Runtime.InteropServices;
using System.Text;

class VolReader {
    // Mixer API
    [DllImport("winmm.dll")] static extern int mixerOpen(out int phmx, uint uMxId, IntPtr dwCallback, IntPtr dwInstance, uint fdwOpen);
    [DllImport("winmm.dll")] static extern int mixerClose(int hmx);
    [DllImport("winmm.dll")] static extern int mixerGetNumDevs();
    
    const int MIXER_GETLINEINFOF_COMPONENTTYPE = 0x00000001;
    const int MIXER_GETLINECONTROLSF_ONEBYTYPE = 0x00000002;
    const int MIXER_GETCONTROLDETAILSF_VALUE = 0x00000000;
    const int MIXERLINE_COMPONENTTYPE_DST_SPEAKERS = 0x00000004;
    const int MIXERCONTROL_CONTROLTYPE_VOLUME = 0x50030001;
    
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct MIXERLINE {
        public int cbStruct;
        public int dwDestination;
        public int dwSource;
        public int dwLineID;
        public int dwUser;
        public int dwComponentType;
        public int cChannels;
        public int cConnections;
        public int cControls;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 16)] public string szShortName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szName;
        public IntPtr dwReserved; // simplified
    }
    
    [StructLayout(LayoutKind.Sequential)]
    public struct MIXERLINECONTROLS {
        public int cbStruct;
        public int dwLineID;
        public int dwControlType;
        public int cControls;
        public int cbmxctrl;
        public IntPtr pamxctrl;
    }
    
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct MIXERCONTROL {
        public int cbStruct;
        public int dwControlID;
        public int dwControlType;
        public int fdwCustom;
        public int cMultipleItems;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 16)] public string szShortName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szName;
        public Bounds bounds;
        
        // metadata
        [StructLayout(LayoutKind.Sequential)]
        public struct Bounds { public int lMinimum; public int lMaximum; 
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)] public int[] reserved; }
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MIXERCONTROLDETAILS {
        public int cbStruct;
        public int dwControlID;
        public int cChannels;
        public int item;
        public IntPtr paDetails;
    }

    static void Main() {
        try {
            int numDevs = mixerGetNumDevs();
            Console.Error.WriteLine("mixerDevs=" + numDevs);
            
            if (numDevs <= 0) { Console.WriteLine("-1"); return; }
            
            int hMixer = 0;
            int ret = mixerOpen(out hMixer, 0, IntPtr.Zero, IntPtr.Zero, 0);
            Console.Error.WriteLine("mixerOpen=" + ret + " handle=" + hMixer);
            if (ret != 0 || hMixer == 0) { Console.WriteLine("-2"); return; }
            
            var line = new MIXERLINE { cbStruct = Marshal.SizeOf<MIXERLINE>(), dwComponentType = MIXERLINE_COMPONENTTYPE_DST_SPEAKERS };
            ret = mixerGetLineInfoA(hMixer, ref line, MIXER_GETLINEINFOF_COMPONENTTYPE);
            Console.Error.WriteLine("lineInfo=" + ret + " name=[" + line.szName.Trim() + "] cControls=" + line.cControls);
            if (ret != 0 || line.cControls == 0) { mixerClose(hMixer); Console.WriteLine("-3"); return; }
            
            int ctrlSize = Marshal.SizeOf<MIXERCONTROL>();
            IntPtr pCtrlBuf = Marshal.AllocCoTaskMem(ctrlSize);
            
            var lc = new MIXERLINECONTROLS { cbStruct = Marshal.SizeOf<MIXERLINECONTROLS>(), dwLineID = line.dwLineID, dwControlType = MIXERCONTROL_CONTROLTYPE_VOLUME, cControls = 1, cbmxctrl = ctrlSize, pamxctrl = pCtrlBuf };
            ret = mixerGetLineControlsA(hMixer, ref lc, MIXER_GETLINECONTROLSF_ONEBYTYPE);
            Console.Error.WriteLine("lineControls=" + ret);
            if (ret != 0) { Marshal.FreeCoTaskMem(pCtrlBuf); mixerClose(hMixer); Console.WriteLine("-4"); return; }
            
            var ctrl = Marshal.PtrToStructure<MIXERCONTROL>(pCtrlBuf);
            Console.Error.WriteLine("control=" + ctrl.szShortName.Trim() + " min=" + ctrl.bounds.lMinimum + " max=" + ctrl.bounds.lMaximum + " id=" + ctrl.dwControlID);
            
            IntPtr pVal = Marshal.AllocCoTaskMem(4);
            Marshal.WriteInt32(pVal, 0);
            
            var det = new MIXERCONTROLDETAILS { cbStruct = Marshal.SizeOf<MIXERCONTROLDETAILS>(), dwControlID = ctrl.dwControlID, cChannels = 1, item = 0, paDetails = pVal };
            ret = mixerGetControlDetailsA(hMixer, ref det, MIXER_GETCONTROLDETAILSF_VALUE);
            if (ret == 0) {
                int val = Marshal.ReadInt32(pVal);
                double pct = (double)(val - ctrl.bounds.lMinimum) / Math.Max(1, ctrl.bounds.lMaximum - ctrl.bounds.lMinimum) * 100.0;
                Console.WriteLine(Math.Round(pct).ToString());
                Console.Error.WriteLine("OK:" + val.ToString() + " pct=" + pct.ToString("F1"));
            } else {
                Console.WriteLine("-5");
                Console.Error.WriteLine("detailErr=" + ret);
            }
            
            Marshal.FreeCoTaskMem(pVal);
            Marshal.FreeCoTaskMem(pCtrlBuf);
            mixerClose(hMixer);
        } catch (Exception ex) {
            Console.WriteLine("-99");
            Console.Error.WriteLine("EX:" + ex.GetType().Name + ":" + ex.Message);
        }
    }
    
    // Need explicit P/Invoke with exact name match
    [DllImport("winmm.dll", CharSet = CharSet.Ansi, EntryPoint = "mixerGetLineInfoA")]
    static extern int mixerGetLineInfoA(int hmx, ref MIXERLINE pmxl, uint fdwInfo);
    
    [DllImport("winmm.dll", CharSet = CharSet.Ansi, EntryPoint = "mixerGetLineControlsA")]
    static extern int mixerGetLineControlsA(int hmx, ref MIXERLINECONTROLS pmxlc, uint fdwControls);
    
    [DllImport("winmm.dll", CharSet = CharSet.Ansi, EntryPoint = "mixerGetControlDetailsA")]
    static extern int mixerGetControlDetailsA(int hmx, ref MIXERCONTROLDETAILS pmxcd, uint fdwDetails);
}
'''

with open(src, "w") as f:
    f.write(cs_code)

r = subprocess.run([csc, "/target:exe", "/out:" + exe, "/nologo", src], capture_output=True, text=True, timeout=30)
print(f"编译 exit={r.returncode}")
if r.stderr.strip():
    print(f"stderr: {r.stderr[:400]}")
if os.path.exists(exe):
    print("\n执行:")
    r2 = subprocess.run([exe], capture_output=True, text=True, timeout=10, errors="replace")
    print(f"exit={r2.returncode} stdout=[{r2.stdout}] stderr=[{r2.stderr}]")
else:
    print("编译失败!")
