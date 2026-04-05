Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$lockPath = ".\state\futures_bot.lock"
$logPath = ".\logs\futures_bot.log"

$lockPid = $null
if (Test-Path $lockPath) {
    try {
        $raw = (Get-Content $lockPath -Raw).Trim()
        if ($raw -match "^\d+$") { $lockPid = [int]$raw }
    }
    catch {}
}

$procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -match "src\.main_futures"
})

$running = if ($procs.Count -gt 0) { $true } else { $false }
$pidText = if ($running) { ($procs[0].ProcessId) } else { "n/a" }
if (-not $lockPid -and $running -and (Test-Path $lockPath)) {
    # On Windows, the lock file may be unreadable while an exclusive byte lock is held.
    # Fall back to current process PID for a useful status display.
    $lockPid = [int]$procs[0].ProcessId
}

Write-Host "=== Futures Bot Status ===" -ForegroundColor Cyan
Write-Host ("Lock file: {0}" -f ($(if (Test-Path $lockPath) { "present" } else { "missing" })))
Write-Host ("Lock PID: {0}" -f $(if ($lockPid) { $lockPid } else { "n/a" }))
Write-Host ("src.main_futures running: {0}" -f $(if ($running) { "yes (PID $pidText)" } else { "no" }))

if (Test-Path $logPath) {
    $tail = Get-Content $logPath -Tail 10
    if ($tail) {
        Write-Host "Last log lines:" -ForegroundColor DarkGray
        $tail | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    }
}
