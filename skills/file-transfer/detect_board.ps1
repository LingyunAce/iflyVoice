# detect_board.ps1 — Auto-detect RK3576 board connection (dynamic IP)
# Usage: powershell -File detect_board.ps1

$user = "cat"
$cred_file = "$PSScriptRoot\..\..\.board_creds"
if (Test-Path $cred_file) {
    $password = (Get-Content $cred_file -Raw).Trim()
} else {
    $password = ""
    Write-Host "[WARN] No .board_creds file" -ForegroundColor Yellow
}
$outfile = "$PSScriptRoot\board_connection.json"

Write-Host "=== Detect RK3576 ==="

# Helper: try SSH on an IP
function Test-BoardSSH($ip) {
    $tcp = Test-NetConnection -ComputerName $ip -Port 22 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
    return ($tcp.TcpTestSucceeded -eq $true)
}

# 1. USB RNDIS first — find adapter and scan subnet
$usb_found = $false
$rndis = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match "RNDIS|Remote NDIS" -and $_.Status -eq "Up" }
if ($rndis) {
    $rndis_ip = (Get-NetIPAddress -InterfaceIndex $rndis.ifIndex -AddressFamily IPv4).IPAddress
    Write-Host "[RNDIS] Adapter found: $($rndis.Name), Windows IP: $rndis_ip"

    if ($rndis_ip) {
        # Try common DHCP-assigned IPs first (fast path)
        $base = $rndis_ip -replace '\.\d+$', '.'
        $candidates = @("$($base)2", "$($base)100", "$($base)1")
        foreach ($ip in $candidates) {
            if (Test-Connection -ComputerName $ip -Count 1 -Quiet 2>$null) {
                Write-Host "[OK] USB DHCP: $ip"
                @{method="usb"; ip=$ip; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
                exit 0
            }
        }
        # Slow scan: test SSH on .2-.10
        foreach ($i in 2..10) {
            $ip = "$($base)$i"
            if (Test-BoardSSH $ip) {
                Write-Host "[OK] USB scan: $ip"
                @{method="usb"; ip=$ip; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
                exit 0
            }
        }
    }
    Write-Host "[RNDIS] Adapter found but no SSH response" -ForegroundColor Yellow
}

# 2. USB static IP fallbacks
$static_ips = @("169.254.184.100", "192.168.137.2", "10.0.0.2")
foreach ($ip in $static_ips) {
    if (Test-BoardSSH $ip) {
        Write-Host "[OK] USB static: $ip"
        @{method="usb"; ip=$ip; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
        exit 0
    }
}

# 3. Ethernet (last resort — requires network config)
if (Test-BoardSSH "192.168.1.207") {
    Write-Host "[OK] ETH: 192.168.1.207"
    @{method="eth"; ip="192.168.1.207"; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
    exit 0
}

# 4. Check for USB device without IP
$devs = Get-PnpDevice 2>$null | Where-Object {
    $_.FriendlyName -match "rk3576|rockchip|gadget|rndis|lubancat|CH341"
}
if ($devs) {
    Write-Host "[DEV] USB found, no IP:" -ForegroundColor Yellow
    $devs | ForEach-Object { Write-Host "  $($_.FriendlyName) [$($_.Status)]" }
} else {
    Write-Host "[NONE] No board" -ForegroundColor Red
}
@{method="none"; ip=""; user=$user; password=$password} | ConvertTo-Json | Out-File -Encoding UTF8 $outfile
exit 1
