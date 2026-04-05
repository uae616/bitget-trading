param(
    [int]$IntervalSeconds = 15,
    [int]$NearMissCount = 5,
    [string]$ExternalScannerPath = "C:\Users\Administrator\3D Objects\WORKSPACE",
    [string]$ExternalSignalsPattern = "detailed_signals_*.csv",
    [int]$ExternalTopN = 5,
    [int]$ExternalFreshMaxMinutes = 10,
    [switch]$Once,
    [switch]$AllowStaleExternalSignals
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

Write-Host "Starting unified monitor..." -ForegroundColor Cyan
Write-Host "Scanner path: $ExternalScannerPath" -ForegroundColor DarkGray

$argsList = @(
    ".\scripts\monitor.ps1",
    "-IntervalSeconds", "$IntervalSeconds",
    "-NearMissCount", "$NearMissCount",
    "-ExternalScannerPath", "$ExternalScannerPath",
    "-ExternalSignalsPattern", "$ExternalSignalsPattern",
    "-ExternalTopN", "$ExternalTopN",
    "-ExternalFreshMaxMinutes", "$ExternalFreshMaxMinutes",
    "-StartExternalScanner"
)

if ($AllowStaleExternalSignals) {
    $argsList += "-AllowStaleExternalSignals"
}
if ($Once) {
    $argsList += "-Once"
}

& powershell -ExecutionPolicy Bypass -File $argsList[0] @($argsList[1..($argsList.Count - 1)])
