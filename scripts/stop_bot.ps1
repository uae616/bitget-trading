Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$stopped = $false
$lockPath = ".\state\bot.lock"

if (Test-Path $lockPath) {
    try {
        $pidText = (Get-Content $lockPath -Raw).Trim()
        if ($pidText -match "^\d+$") {
            $lockPid = [int]$pidText
            try {
                Stop-Process -Id $lockPid -Force -ErrorAction Stop
                Write-Host "Stopped bot process from lock file PID: $lockPid" -ForegroundColor Green
                $stopped = $true
            }
            catch {
                Write-Host "Lock-file PID not running: $lockPid" -ForegroundColor Yellow
            }
        }
    }
    catch {
        # lock file currently held; fallback scan below will handle stop
    }
}

if (-not $stopped) {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -match "src\.main"
    }

    if ($procs) {
        foreach ($p in $procs) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                Write-Host "Stopped bot process: $($p.ProcessId)" -ForegroundColor Green
                $stopped = $true
            }
            catch {
                Write-Host "Could not stop process: $($p.ProcessId)" -ForegroundColor Yellow
            }
        }
    }
}

if (-not $stopped) {
    Write-Host "No running src.main bot process found." -ForegroundColor Yellow
}

if (Test-Path $lockPath) {
    try {
        $pidText = (Get-Content $lockPath -Raw).Trim()
        if ($pidText -match "^\d+$") {
            $lockPid = [int]$pidText
            $alive = $false
            try {
                $null = Get-Process -Id $lockPid -ErrorAction Stop
                $alive = $true
            }
            catch {}

            if (-not $alive) {
                Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
                Write-Host "Removed stale lock file (PID: $lockPid)." -ForegroundColor Yellow
            }
        }
    }
    catch {}
}
