// Final attempt: multiple approaches to read system master volume
using System;
using System.Runtime.InteropServices;

class VolRead {
    // ── Approach 1: Direct COM vtable call via IUnknown ──
    
    // IUnknown
    [DllImport("ole32.dll")] static extern int CoInitialize(IntPtr pvReserved);
    [DllImport("ole32.dll")] static extern void CoUninitialize();
    
    // For COM calls via raw vtable
    [DllImport("ole32.dll")] static extern int CoCreateInstance(
        [MarshalAs(UnmanagedType.LPStruct)] Guid rclsid,
        IntPtr pUnkOuter, uint dwClsContext,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid,
        out IntPtr ppv);
    
    // ── Approach 2: waveOutGetVolume ──
    [DllImport("winmm.dll")] public static extern uint waveOutGetVolume(IntPtr hwo, out uint pdwVolume);
    
    // ── GUIDs ──
    static readonlyGuid CLSID_MMDevEnum = new Guid("{BCDE0395-E52F-467C-8E3D-C57293534E89}");
    static readonlyGuid IID_IMMDeviceEnumerator = new Guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}");
    static readonlyGuid IID_IMMDevice = new Guid("{D666063F-1587-4E43-81F1-B948E5B53D97}");
    static readonlyGuid IID_IAudioEndpointVolume = new Guid("{5CDF2C82-841E-4546-9722-0CF74078229A}");
    static readonlyGuid IID_IAudioClient = new Guid("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}");
    
    static IntPtr ComCall(IntPtr pObj, int vtableIndex, params object[] args) {
        // Read vtable pointer
        IntPtr vtbl = Marshal.ReadIntPtr(pObj);
        // Get function pointer at vtable[index]
        IntPtr fnPtr = Marshal.ReadIntPtr(vtbl, vtableIndex * IntPtr.Size);
        // This would need complex marshaling - skip for now
        return IntPtr.Zero;
    }
    
    static void Main() {
        Console.Error.WriteLine("=== Attempt 1: CoCreateInstance MMDeviceEnumerator ===");
        try {
            CoInitialize(IntPtr.Zero);
            IntPtr pEnum = 0;
            int hr = CoCreateInstance(CLSID_MMDeviceEnumerator, 0, 1 /*CLSCTX_INPROC_SERVER*/, 
                IID_IMMDeviceEnumerator, out pEnum);
            Console.Error.WriteLine("CoCreateInstance hr=0x" + hr.ToString("X8") + " ptr=" + pEnum.ToString());
            
            if (hr >= 0 && pEnum != IntPtr.Zero) {
                Console.Error.WriteLine("COM AVAILABLE! Would need vtable dispatch to proceed.");
            }
            CoUninitialize();
        } catch (Exception e) {
            Console.Error.WriteLine("COM_EX: " + e.Message);
        }
        
        Console.Error.WriteLine("\n=== Attempt 2: waveOutGetVolume ===");
        try {
            uint v;
            waveOutGetVolume(IntPtr.Zero, out v);
            int lo = (int)(v & 0xFFFF); int hi = (int)((v >> 16) & 0xFFFF);
            int avg = (lo + hi) / 2 * 100 / 0xFFFF;
            Console.Error.WriteLine("waveout raw=0x" + v.ToString("X8") + " avg=" + avg + "%");
        } catch(Exception e) { Console.Error.WriteLine("waveout_ex:" + e.Message); }
        
        Console.Error.WriteLine("\n=== Attempt 3: Check if nircmd setsysvolume works ===");
        // Just report status
        
        Console.WriteLine("-1");
        Console.Error.WriteLine("ALL_FAILED");
    }
}
