<#
.SYNOPSIS
    LogChain - Network & Port Pre-Flight Check (PowerShell)
.DESCRIPTION
    Validates IP addresses, port availability, peer reachability, MongoDB isolation,
    and Geth consensus compatibility for two-laptop demo setups.
#>

param (
    [string]$Role = "device1",  # "device1", "device2", or "friend"
    [string]$PeerIP = ""
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " LogChain - Network & Port Pre-Flight Check (Role: $Role)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Local IPv4 Addresses
Write-Host "`n[*] Local IPv4 Addresses:" -ForegroundColor Yellow
$LocalIPs = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -ExpandProperty IPAddress
foreach ($ip in $LocalIPs) {
    Write-Host "    - $ip" -ForegroundColor Green
}

# 2. Peer Reachability
if ($PeerIP -ne "") {
    Write-Host "`n[*] Checking Peer Reachability ($PeerIP)..." -ForegroundColor Yellow
    $ping = Test-Connection -ComputerName $PeerIP -Count 2 -Quiet
    if ($ping) {
        Write-Host "  [PASS] Ping to peer $PeerIP succeeded." -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Ping to peer $PeerIP failed or ICMP is blocked by firewall." -ForegroundColor Yellow
    }
}

# 3. Port Checks by Role
Write-Host "`n[*] Checking Local Port Bindings & Firewall Requirements:" -ForegroundColor Yellow

function Test-LocalPort ($port, $name, $required) {
    $conn = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue
    if ($conn.TcpTestSucceeded) {
        Write-Host "  [LISTENING] Port $port ($name) is ACTIVE" -ForegroundColor Green
    } else {
        if ($required) {
            Write-Host "  [CLOSED]    Port $port ($name) is NOT listening" -ForegroundColor Yellow
        } else {
            Write-Host "  [AVAILABLE] Port $port ($name) is free" -ForegroundColor Gray
        }
    }
}

if ($Role -eq "device1") {
    Test-LocalPort 30303 "Device 1 P2P" $false
    Test-LocalPort 8545  "Device 1 RPC" $false
    Test-LocalPort 5000  "Flask Dashboard & Ingest" $false
    Test-LocalPort 27017 "MongoDB (Localhost only)" $false
} elseif ($Role -eq "device2") {
    Test-LocalPort 30304 "Device 2 P2P" $false
    Test-LocalPort 8546  "Device 2 RPC" $false
} elseif ($Role -eq "friend") {
    Write-Host "  Friend role requires outbound connectivity to Device 1 port 5000." -ForegroundColor Gray
}

# 4. MongoDB Localhost-Only Isolation Check
Write-Host "`n[*] Verifying MongoDB Isolation:" -ForegroundColor Yellow
try {
    # Check if MongoDB is bound to external interface
    $mongoListeners = Get-NetTCPConnection -LocalPort 27017 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalAddress
    if ($mongoListeners) {
        $exposed = $mongoListeners | Where-Object { $_ -eq "0.0.0.0" -or $_ -notin @("127.0.0.1", "::1") }
        if ($exposed) {
            Write-Host "  [WARN] MongoDB is listening on $exposed. For security, bind to 127.0.0.1 only!" -ForegroundColor Yellow
        } else {
            Write-Host "  [PASS] MongoDB is bound strictly to localhost: $mongoListeners" -ForegroundColor Green
        }
    } else {
        Write-Host "  [INFO] MongoDB is not running locally on port 27017." -ForegroundColor Gray
    }
} catch {
    Write-Host "  [INFO] Could not inspect net connections directly." -ForegroundColor Gray
}

# 5. Toolchain checks
Write-Host "`n[*] Toolchain Verification:" -ForegroundColor Yellow
$tools = @("python", "git", "curl")
foreach ($t in $tools) {
    if (Get-Command $t -ErrorAction SilentlyContinue) {
        Write-Host "  [PASS] $t found" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $t not found in PATH" -ForegroundColor Red
    }
}

# 6. Geth Version Check
Write-Host "`n[*] Geth Compatibility Check:" -ForegroundColor Yellow
$localGeth = ".\bin\geth.exe"
if (Test-Path $localGeth) {
    $out = & $localGeth version
    if ($out -match "1\.13\.") {
        Write-Host "  [PASS] Pinned Geth v1.13.x found at $localGeth (Clique PoA supported)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Incompatible Geth version at $($localGeth): $out" -ForegroundColor Red
    }
} else {
    $sysGeth = Get-Command geth -ErrorAction SilentlyContinue
    if ($sysGeth) {
        $out = & geth version
        if ($out -match "1\.13\.") {
            Write-Host "  [PASS] Geth v1.13.x found in PATH (Clique PoA supported)" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] Geth >= 1.14 detected. Clique PoA sealing is unsupported! Run: python scripts/download_geth.py" -ForegroundColor Red
        }
    } else {
        Write-Host "  [FAIL] Geth binary not found. Run: python scripts/download_geth.py" -ForegroundColor Red
    }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " Recommended Windows Firewall Commands (Run as Admin if needed):" -ForegroundColor Cyan
Write-Host " Device 1:" -ForegroundColor Gray
Write-Host "   New-NetFirewallRule -DisplayName 'LogChain P2P D1' -Direction Inbound -LocalPort 30303 -Protocol TCP -Action Allow"
Write-Host "   New-NetFirewallRule -DisplayName 'LogChain P2P D1 UDP' -Direction Inbound -LocalPort 30303 -Protocol UDP -Action Allow"
Write-Host "   New-NetFirewallRule -DisplayName 'LogChain Dashboard' -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow"
Write-Host " Device 2:" -ForegroundColor Gray
Write-Host "   New-NetFirewallRule -DisplayName 'LogChain P2P D2' -Direction Inbound -LocalPort 30304 -Protocol TCP -Action Allow"
Write-Host "   New-NetFirewallRule -DisplayName 'LogChain P2P D2 UDP' -Direction Inbound -LocalPort 30304 -Protocol UDP -Action Allow"
Write-Host "============================================================" -ForegroundColor Cyan
