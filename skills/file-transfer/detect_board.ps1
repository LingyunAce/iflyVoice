# detect_board.ps1 — Auto-detect RK3576 board connection
# Usage: powershell -File detect_board.ps1

$user = "cat"
# Read password from file (not committed to git)
$cred_file = "$PSScriptRoot\..\..\.board_creds"
if (Test-Path $cred_file) {
    $password = (Get-Content $cred_file -Raw).Trim()
} else {
    $password = ""
    Write-Host "[WARN] No .board_creds file — create it with the board password" -ForegroundColor Yellow
}
$outfile = "$PSScriptRoot\board_connection.json"

Write-Host "=== Detect RK3576 ==="

# 1. Try SSH (ethernet)
$ssh_ip = "192.168.1.207"
if (Test-Connection -ComputerName $ssh_ip -Count 1 -Quiet 2>$null) {
    Write-Host "[OK] SSH: $ssh_ip"
    @{method="ssh"; ip=$ssh_ip; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
    exit 0
}

# 2. Try USB RNDIS gadget IPs (169.254.x.x = link-local)
$usb_ips = @("169.254.184.100", "192.168.137.2", "192.168.137.1", "169.254.1.2", "10.0.0.2")
foreach ($ip in $usb_ips) {
    if (Test-Connection -ComputerName $ip -Count 1 -Quiet 2>$null) {
        Write-Host "[OK] USB: $ip"
        @{method="usb"; ip=$ip; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
        exit 0
    }
}

# 3. Scan USB devices
$devs = Get-PnpDevice 2>$null | Where-Object {
    $_.FriendlyName -match "rk3576|rockchip|gadget|rndis|lubancat|USB Serial"
}
if ($devs) {
    Write-Host "[DEV] USB device found, no IP:"
    $devs | ForEach-Object { Write-Host "  $($_.FriendlyName) [$($_.Status)]" }
} else {
    Write-Host "[NONE] No board detected"
}
@{method="none"; ip=""; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
exit 1
