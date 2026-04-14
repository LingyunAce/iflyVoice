$m = Get-WmiObject -Namespace root\WMI -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1
if ($m) {
    $m.WmiSetBrightness(1, 60)
    Write-Host "OK"
} else {
    Write-Host "ERR"
}
