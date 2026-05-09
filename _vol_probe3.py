"""编译并测试多种读取系统主音量的方案"""
import subprocess
import os
import json
import sys

CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
BASE = os.path.dirname(__file__ or ".")
EXE = os.path.join(BASE, "_vol_read.exe")
SRC = os.path.join(BASE, "_vol_read.cs")

code = r'''
using System;
using System.Runtime.InteropServices;
using System.Text;

// ── 方案1: WinMM Mixer API (老式音频混合器，不依赖 CoreAudio COM) ──
class VolRead {
    // ── Mixer API P/Invoke ──
    [DllImport("winmm.dll")] static extern int mixerOpen(out int phmx, uint uMxId, IntPtr dwCallback, IntPtr dwInstance, uint fdwOpen);
    [DllImport("winmm.dll")] static extern int mixerClose(int hmx);
    [DllImport("winmm.dll")] static extern int mixerGetNumDevs();
    
    [DllImport("winmm.dll")] static extern int mixerGetLineInfoA(int hmx, ref MIXERLINEINFO pmxl, uint fdwInfo);
    [DllImport("winmm.dll")] static extern int mixerGetLineControlsA(int hmx, ref MIXERLINECONTROLS pmxlc, uint fdwControls);
    [DllImport("winmm.dll")] static extern int mixerGetControlDetailsA(int hmx, ref MIXERCONTROLDETAILS pmxcd, uint fdwDetails);

    const int MIXER_OBJECT_WAVEOUT = 0x00000000;
    const int MIXER_LINE_COMPONENTTYPE_DST = 0x00000003;  // destination line
    const int MIXERLINE_COMPONENTTYPE_DST_SPEAKERS = 0x00000004;  // speakers destination
    const int MIXER_GETLINEINFOF_COMPONENTTYPE = 0x00000001;
    const int MIXER_GETLINECONTROLSF_ONEBYTYPE = 0x00000002;
    const int MIXERCONTROL_CONTROLTYPE_VOLUME = 0x50030001;
    const int MIXERCONTROL_CONTROLTYPE_MUTE = 0x50020001;
    const int MIXER_GETCONTROLDETAILSF_VALUE = 0x00000000;
    const int MIXER_SETCONTROLDETAILSF_VALUE = 0x00000000;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    struct MIXERLINEINFO {
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
    }

    [StructLayout(LayoutKind.Sequential)]
    struct MIXERLINECONTROLS {
        public int cbStruct;
        public int dwLineID;
        public int dwControlType;
        public int cControls;
        public int cbmxctrl;
        public IntPtr pamxctrl;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct MIXERCONTROL {
        public int cbStruct;
        public int dwControlID;
        public int dwControlType;
        public int fdwCustom;
        public int cMultipleItems;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 16)] public string szShortName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szName;
        public int lMinimum;
        public int lMaximum;
        public int lStep;
        public int cMultipleItems;
        public int dwReserved1..6;  // padding
    }

    // Simplified for our use case
    [StructLayout(LayoutKind.Sequential)]
    struct MIXERCONTROL_DETAILS {
        public int cbStruct;
        public int dwControlID;
        public int cChannels;
        public int item;
        public IntPtr paDetails;
    }

    // ── 方案2: IAudioEndpointVolume via CoCreateInstance + vtable dispatch ──
    // This is risky because COM may not be registered
    
    // ── 方案3: waveOutGetVolume (already known to return wave device vol) ──
    [DllImport("winmm.dll")]
    public static extern uint waveOutGetVolume(IntPtr hwo, out uint pdwVolume);
    
    // ── 方案4: DirectSound via dsound.dll ──
    // (probably won't work either)

    static void Main(string[] args) {
        StringBuilder sb = new StringBuilder();
        
        // === 方案1: Mixer API ===
        try {
            int numDevs = mixerGetNumDevs();
            sb.Append($"MixerAPI: devs={numDevs} ");
            
            if (numDevs > 0) {
                int hMixer = 0;
                int ret = mixerOpen(out hMixer, 0, IntPtr.Zero, IntPtr.Zero, 0);  // WAVE mapper
                sb.Append($"open={ret} ");
                
                if (ret == 0 && hMixer != 0) {
                    // Try to get speaker destination line
                    var mli = new MIXERLINEINFO { cbStruct = Marshal.SizeOf<MIXERLINEINFO>(), dwComponentType = MIXERLINE_COMPONENTTYPE_DST_SPEAKERS };
                    ret = mixerGetLineInfoA(hMixer, ref mli, MIXER_GETLINEINFOF_COMPONENTTYPE);
                    sb.Append($"lineinfo={ret} ");
                    
                    if (ret == 0) {
                        sb.Append($"name=[{mli.szName.Trim()}] cControls={mli.cControls} ");
                        
                        // Get volume control
                        var mlc = new MIXERLINECONTROLS {
                            cbStruct = Marshal.SizeOf<MIXERLINECONTROLS>(),
                            dwLineID = mli.dwLineID,
                            dwControlType = MIXERCONTROL_CONTROLTYPE_VOLUME,
                            cControls = 1,
                            cbmxctrl = 152, // approximate size
                        };
                        
                        // Allocate unmanaged memory for control details
                        IntPtr pCtrl = Marshal.AllocCoTaskMem(152);
                        mlc.pamxctrl = pCtrl;
                        ret = mixerGetLineControlsA(hMixer, ref mlc, MIXER_GETLINECONTROLSF_ONEBYTYPE);
                        sb.Append($"ctrl={ret} ");
                        
                        if (ret == 0) {
                            var ctrl = Marshal.PtrToStructure<MIXERCONTROL>(pCtrl);
                            sb.Append($"ctrlname=[{ctrl.szShortName.Trim()}] min={ctrl.lMinimum} max={ctrl.lMaximum} ");
                            
                            // Read current value
                            int val = 0;
                            IntPtr pVal = Marshal.AllocCoTaskMem(4);
                            Marshal.WriteInt32(pVal, 0);
                            
                            var mcd = new MIXERCONTROL_DETAILS {
                                cbStruct = Marshal.SizeOf<MIXERCONTROL_DETAILS>(),
                                dwControlID = ctrl.dwControlID,
                                cChannels = 1,
                                item = 0,
                                paDetails = pVal,
                            };
                            ret = mixerGetControlDetailsA(hMixer, ref mcd, MIXER_GETCONTROLDETAILSF_VALUE);
                            
                            if (ret == 0) {
                                val = Marshal.ReadInt32(pVal);
                                double pct = (double)(val - ctrl.lMinimum) / (ctrl.lMaximum - ctrl.lMinimum) * 100.0;
                                sb.Append($"VOL={val} ({pct:F1}%)");
                                
                                Console.WriteLine(Math.Round(pct).ToString());
                                Console.Error.WriteLine("MIXER_API");
                            } else {
                                sb.Append($"detail_err={ret}");
                                Console.WriteLine("-2");
                                Console.Error.WriteLine("MIXER_DETAIL_ERR:" + ret.ToString());
                            }
                            
                            Marshal.FreeCoTaskMem(pVal);
                        } else {
                            sb.Append($"no_ctrl ");
                            Console.WriteLine("-3");
                            Console.Error.WriteLine("MIXER_NO_CTRL");
                        }
                        
                        Marshal.FreeCoTaskMem(pCtrl);
                    } else {
                        sb.Append($"no_line ");
                    }
                    
                    mixerClose(hMixer);
                } else {
                    sb.Append($"cant_open ");
                }
            }
            
            Console.Error.WriteLine(sb.ToString());
        } catch (Exception ex) {
            Console.WriteLine("-99");
            Console.Error.WriteLine("MIXER_EX:" + ex.Message);
        }
        
        // === 方案3: waveOut fallback ===
        try {
            uint v;
            waveOutGetVolume(IntPtr.Zero, out v);
            int lo = (int)(v & 0xFFFF);
            int hi = (int)((v >> 16) & 0xFFFF);
            int avg = (lo + hi) / 2 * 100 / 0xFFFF;
            Console.Error.WriteLine($"WAVEOUT: raw=0x{v:X8} lo={lo} hi={hi} pct={avg}");
        } catch {}
    }
}
'''

print("=" * 60)
print("编译 C# 音量读取程序...")
print("=" * 60)

with open(SRC, "w") as f:
    f.write(code)

r = subprocess.run(
    [CSC, "/target:exe", "/out:" + EXE, "/nologo", "/unsafe", SRC],
    capture_output=True, text=True, timeout=30,
)
print(f"编译 exit={r.returncode}")
if r.stderr.strip():
    print(f"stderr: {r.stderr[:500]}")
if r.stdout.strip():
    print(f"stdout: {r.stdout[:200]}")

if not os.path.exists(EXE):
    print("编译失败!")
else:
    print("\n执行:")
    r2 = subprocess.run([EXE], capture_output=True, text=True, timeout=10)
    print(f"exit={r2.returncode}")
    print(f"stdout=[{r2.stdout}]")
    print(f"stderr=[{r2.stderr}]")
    
    out = r2.stdout.strip()
    if out.isdigit() and int(out) >= 0:
        print(f"\n>>> 系统主音量 ≈ {out}% <<<")
