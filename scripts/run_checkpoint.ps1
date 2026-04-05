param(
    [int]$Cycles = 50,
    [int]$FastCycleSeconds = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$pythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$beforeFile = ".\state\checkpoint_before.json"
$afterFile = ".\state\checkpoint_after.json"
$reportFile = ".\state\checkpoint_report.json"
$configPath = ".\config.toml"

$cfgBackup = Get-Content $configPath -Raw

try {
    & $pythonExe .\scripts\checkpoint_metrics.py snapshot $beforeFile
    if ($LASTEXITCODE -ne 0) { throw "Failed to capture before snapshot." }

    $state = Get-Content .\state\state.json -Raw | ConvertFrom-Json
    $startCycle = [int]$state.meta.cycle
    $targetCycle = $startCycle + $Cycles
    Write-Host "Checkpoint start cycle: $startCycle" -ForegroundColor Cyan
    Write-Host "Checkpoint target cycle: $targetCycle" -ForegroundColor Cyan

    .\scripts\stop_bot.ps1 | Out-Host

    $cfgNow = Get-Content $configPath -Raw
    if ($FastCycleSeconds -gt 0) {
        $cfgNow = [regex]::Replace($cfgNow, "(?m)^\s*cycle_seconds\s*=\s*\d+\s*$", "cycle_seconds = $FastCycleSeconds")
    }

    if ($cfgNow -match "(?m)^\s*max_cycles\s*=\s*\d+\s*$") {
        $cfgNow = [regex]::Replace($cfgNow, "(?m)^\s*max_cycles\s*=\s*\d+\s*$", "max_cycles = $targetCycle")
    }
    elseif ($cfgNow -match "(?m)^\[bot\]\s*$") {
        $cfgNow = [regex]::Replace($cfgNow, "(?m)^\[bot\]\s*$", "[bot]`r`nmax_cycles = $targetCycle", 1)
    }
    else {
        throw "config.toml has no [bot] section. Add it before running checkpoint."
    }

    Set-Content $configPath $cfgNow -Encoding UTF8

    $env:PYTHONPATH = "."
    $runner = Start-Process -FilePath $pythonExe `
        -ArgumentList ".\scripts\experiment_runner.py", "$targetCycle" `
        -WorkingDirectory (Get-Location).Path `
        -NoNewWindow -PassThru

    $lastShownCycle = -1
    while (-not $runner.HasExited) {
        Start-Sleep -Seconds 2
        try {
            $stateNow = Get-Content .\state\state.json -Raw | ConvertFrom-Json
            $currentCycle = [int]$stateNow.meta.cycle
            if ($currentCycle -ne $lastShownCycle) {
                Write-Host ("Checkpoint progress: {0}/{1}" -f $currentCycle, $targetCycle) -ForegroundColor DarkCyan
                $lastShownCycle = $currentCycle
            }
        }
        catch {
            # ignore transient state read issues while bot is writing
        }
    }

    if ($runner.ExitCode -ne 0) {
        throw "experiment_runner.py exited with code $($runner.ExitCode)."
    }

    $stateAfterRun = Get-Content .\state\state.json -Raw | ConvertFrom-Json
    $endCycle = [int]$stateAfterRun.meta.cycle
    if ($endCycle -lt $targetCycle) {
        throw "Checkpoint run ended at cycle $endCycle before target $targetCycle."
    }

    & $pythonExe .\scripts\checkpoint_metrics.py snapshot $afterFile
    if ($LASTEXITCODE -ne 0) { throw "Failed to capture after snapshot." }

    & $pythonExe .\scripts\checkpoint_metrics.py compare $beforeFile $afterFile $reportFile
    if ($LASTEXITCODE -ne 0) { throw "Failed to build checkpoint report." }

    Write-Host "Checkpoint report saved: $reportFile" -ForegroundColor Green
}
finally {
    Set-Content $configPath $cfgBackup -Encoding UTF8
    .\scripts\run_bot.ps1 | Out-Host
}
