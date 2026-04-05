Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$configPath = ".\config.toml"
$lockPath = ".\state\bot.lock"
$logPath = ".\logs\bot.log"
$venvPython = (Resolve-Path ".\.venv\Scripts\python.exe").Path.ToLower()

function Parse-LogTimestamp([string]$line) {
    if (-not $line) { return $null }
    $m = [regex]::Match($line, "^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]")
    if (-not $m.Success) { return $null }
    try {
        return [datetime]::ParseExact($m.Groups[1].Value, "yyyy-MM-dd HH:mm:ss", $null)
    }
    catch {
        return $null
    }
}

function Get-BoolFromConfig([string]$path, [string]$key, [bool]$defaultValue) {
    if (-not (Test-Path $path)) { return $defaultValue }
    $raw = Get-Content $path -Raw
    $m = [regex]::Match($raw, "(?m)^\s*" + [regex]::Escape($key) + "\s*=\s*(true|false)\s*$")
    if (-not $m.Success) { return $defaultValue }
    return ($m.Groups[1].Value.ToLower() -eq "true")
}

$dryRun = Get-BoolFromConfig -path $configPath -key "dry_run" -defaultValue $true
$mode = if ($dryRun) { "DRY_RUN" } else { "LIVE" }

$lockPid = $null
if (Test-Path $lockPath) {
    try {
        $pidText = (Get-Content $lockPath -Raw).Trim()
        if ($pidText -match "^\d+$") {
            $lockPid = [int]$pidText
        }
    }
    catch {
        # lock file may be actively locked; keep null here and rely on process scan
    }
}

$procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -match "src\.main"
})

$venvProc = $null
$otherProcIds = @()
foreach ($p in $procs) {
    $cmd = [string]($p.CommandLine)
    if ($cmd -and $cmd.ToLower() -match [regex]::Escape($venvPython)) {
        $venvProc = $p
    }
    elseif ($lockPid -and [int]$p.ProcessId -eq [int]$lockPid) {
        $venvProc = $p
    }
    else {
        $otherProcIds += $p.ProcessId
    }
}

$runningProc = $venvProc
if (-not $runningProc -and @($procs).Count -gt 0) {
    $runningProc = $procs | Select-Object -First 1
}

$running = $runningProc -ne $null

$lastStartLine = $null
$lastCycleLine = $null
$heartbeatAgeSec = $null
$heartbeatState = "unknown"
if (Test-Path $logPath) {
    $tail = Get-Content $logPath -Tail 250
    $startMatches = $tail | Select-String -Pattern "Bot started\. DRY_RUN="
    if ($startMatches) { $lastStartLine = $startMatches[-1].Line }

    $cycleMatches = $tail | Select-String -Pattern "Cycle \d+ running"
    if ($cycleMatches) { $lastCycleLine = $cycleMatches[-1].Line }

    $heartbeatLine = if ($lastCycleLine) { $lastCycleLine } else { $lastStartLine }
    $ts = Parse-LogTimestamp -line $heartbeatLine
    if ($ts) {
        $heartbeatAgeSec = [int]([datetime]::Now - $ts).TotalSeconds
        if ($heartbeatAgeSec -le 120) {
            $heartbeatState = "fresh"
        }
        else {
            $heartbeatState = "stale"
        }
    }
}

Write-Host "=== Bot Status ===" -ForegroundColor Cyan
$lockState = if (Test-Path $lockPath) { "present" } else { "missing" }
$lockPidText = if ($lockPid) { "$lockPid" } else { "n/a" }
$venvRunText = if ($running) { "yes (PID $($runningProc.ProcessId))" } else { "no" }
Write-Host ("Mode (config): {0}" -f $mode)
Write-Host ("Lock file: {0}" -f $lockState)
Write-Host ("Lock PID: {0}" -f $lockPidText)
Write-Host ("src.main running: {0}" -f $venvRunText)
if ($heartbeatAgeSec -ne $null) {
    $heartbeatText = "{0} ({1}s)" -f $heartbeatState, $heartbeatAgeSec
    if ($heartbeatState -eq "stale") {
        Write-Host ("Log heartbeat: {0}" -f $heartbeatText) -ForegroundColor Yellow
    }
    else {
        Write-Host ("Log heartbeat: {0}" -f $heartbeatText)
    }
}
else {
    Write-Host "Log heartbeat: unknown"
}

if ($lockPid -and $running -and ($lockPid -ne [int]$runningProc.ProcessId)) {
    Write-Host ("Lock/process mismatch: lock PID {0}, running PID {1}" -f $lockPid, $runningProc.ProcessId) -ForegroundColor Yellow
}
if ($otherProcIds.Count -gt 0) {
    Write-Host ("Additional src.main PIDs: {0}" -f ($otherProcIds -join ", ")) -ForegroundColor Yellow
}
else {
    Write-Host "Additional src.main PIDs: none"
}

if ($lastStartLine) {
    Write-Host "Last startup line:" -ForegroundColor DarkGray
    Write-Host $lastStartLine -ForegroundColor DarkGray
}
if ($lastCycleLine) {
    Write-Host "Last cycle line:" -ForegroundColor DarkGray
    Write-Host $lastCycleLine -ForegroundColor DarkGray
}
