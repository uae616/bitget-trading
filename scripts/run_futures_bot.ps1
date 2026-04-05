Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$pythonExe = ".\.venv\Scripts\python.exe"
$lockPath = ".\state\futures_bot.lock"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (Test-Path $lockPath) {
    Write-Host "Futures bot lock file exists: $lockPath" -ForegroundColor Yellow
    Write-Host "If stale, stop previous process and remove lock." -ForegroundColor Yellow
}

$proc = Start-Process -FilePath $pythonExe -ArgumentList "-m", "src.main_futures" -WorkingDirectory (Get-Location) -PassThru
Start-Sleep -Seconds 2
Write-Host "Futures bot started. PID: $($proc.Id)" -ForegroundColor Green
Write-Host "Log file: .\logs\futures_bot.log" -ForegroundColor Green
