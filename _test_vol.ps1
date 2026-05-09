# Test audio COM availability
Write-Host "=== COM Availability Test ==="

# 1. Shell.Application
try {
    $as = New-Object -ComObject Shell.Application
    Write-Host "Shell.Application: OK"
} catch {
    Write-Host "Shell.Application: ERR $($_.Exception.Message)"
}

# 2. MMDeviceEnumerator (CoreAudio)
try {
    $mm = New-Object -ComObject MMDeviceEnumerator
    Write-Host "MMDeviceEnumerator: OK"
    
    # Try to get default endpoint
    $dev = $mm.GetDefaultAudioEndpoint(0, 1)  # eRender, eConsole
    Write-Host "DefaultEndpoint: $($dev.FriendlyName)"
    
    $epVol = $dev.AudioEndpointVolume
    $scalar = $epVol.MasterVolumeLevelScalar
    $pct = [math]::Round($scalar * 100)
    Write-Host "MasterVolumeLevelScalar: $scalar -> ${pct}%"
} catch {
    Write-Host "MMDeviceEnumerator: ERR $($_.Exception.Message)"
}

# 3. nircmd getsysvolume
$nircmd = Join-Path $PSScriptRoot "nircmd.exe"
if (Test-Path $nircmd) {
    $result = & $nircmd getsysvolume 2>&1
    Write-Host "nircmd getsysvolume: exit=$LASTEXITCODE stdout='[$($result)]' len=$($result.Length)"
} else {
    Write-Host "nircmd.exe: NOT FOUND"
}

# 4. waveOutGetVolume via P/Invoke
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class WaveOutVol {
    [DllImport("winmm.dll")]
    public static extern uint waveOutGetVolume(IntPtr hwo, out uint pdwVolume);
    
    public static string Get() {
        uint v;
        waveOutGetVolume(IntPtr.Zero, out v);
        int lo = (int)(v & 0xFFFF);
        int hi = (int)((v >> 16) & 0xFFFF);
        return string.Format("raw=0x{0:X8} lo={1} hi={2} avg_pct={3}", v, lo, hi, (lo + hi) / 2 * 100 / 0xFFFF);
    }
}
'@
Write-Host "waveOutGetVolume: $([WaveOutVol]::Get())"
