# Standalone PowerShell script to test all possible ways of reading system master volume
$ErrorActionPreference = 'Stop'

Write-Host "=== Test 1: MMDeviceEnumerator ComObject ==="
try {
    $mm = New-Object -ComObject MMDeviceEnumerator
    $dev = $mm.GetDefaultAudioEndpoint(0, 1)
    $vol = $dev.AudioEndpointVolume.MasterVolumeLevelScalar * 100
    Write-Host "SUCCESS: $vol"
} catch {
    Write-Host "FAILED: $($_.Exception.Message)"
}

Write-Host "`n=== Test 2: Activator + CLSID ==="
try {
    $guid = [System.Guid]::Parse('BCDE0395-E52F-467C-8E3D-C57293534E89')
    $t = [System.Type]::GetTypeFromCLSID($guid)
    if ($t -ne $null) {
        $o = [System.Activator]::CreateInstance($t)
        $spk = $o.GetDefaultAudioEndpoint(0, 1)
        $v = [math]::Round($spk.AudioEndpointVolume.MasterVolumeLevelScalar * 100)
        Write-Host "SUCCESS: $v"
    } else {
        Write-Host "FAILED: Type is null"
    }
} catch {
    Write-Host "FAILED: $($_.Exception.Message.Substring(0, [Math]::Min(150, $_.Exception.Message.Length)))"
}

Write-Host "`n=== Test 3: C# inline compilation ==="
try {
    $cs = @'
using System;
using System.Runtime.InteropServices;
public class V {
    [DllImport("ole32.dll")] static extern int CoCreateInstance(ref Guid rclsid, IntPtr pUnkOuter, uint dwClsContext, ref Guid riid, out IntPtr ppv);
    public static void Main() {
        var c = new Guid("BCDE0395-E52F-467C-8E3D-C57293534E89");
        var i = new Guid("A95664D2-9614-4F35-A746-DE8DB63617E6");
        IntPtr p; var h = CoCreateInstance(ref c, IntPtr.Zero, 1U, ref i, out p);
        Console.WriteLine("hr=0x" + h.ToString("X8"));
    }
}
'@
    $type = Add-Type -TypeDefinition $cs -Language CSharp -PassThru -ErrorAction SilentlyContinue
    if ($type) { $type::Main() } else { Write-Host "COMPILE_FAILED" }
} catch {
    Write-Host "FAILED: $($_.Exception.Message.Substring(0, [Math]::Min(200, $_.Exception.Message.Length)))"
}

Write-Host "`nDone."
