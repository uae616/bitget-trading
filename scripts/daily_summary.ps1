param(
    [int]$Cycles = 50,
    [int]$FastCycleSeconds = 1,
    [string]$HistoryCsvPath = ".\state\daily_summary_history.csv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

Write-Host "Running checkpoint summary..." -ForegroundColor Cyan
.\scripts\run_checkpoint.ps1 -Cycles $Cycles -FastCycleSeconds $FastCycleSeconds | Out-Host

$reportPath = ".\state\checkpoint_report.json"
if (-not (Test-Path $reportPath)) {
    throw "Checkpoint report not found: $reportPath"
}

$report = Get-Content $reportPath -Raw | ConvertFrom-Json
$before = $report.before
$after = $report.after
$delta = $report.delta

$roiPct = 0.0
if ($null -ne $delta.roi_pct) {
    $roiPct = [double]$delta.roi_pct
}

$netAfterFees = [double]$delta.equity_usdt - [double]$delta.fees_usdt
if ($null -ne $delta.net_after_fees_usdt) {
    $netAfterFees = [double]$delta.net_after_fees_usdt
}

$status = "FLAT"
$statusColor = "Yellow"
if ($netAfterFees -gt 0.0) {
    $status = "PROFIT"
    $statusColor = "Green"
}
elseif ($netAfterFees -lt 0.0) {
    $status = "LOSS"
    $statusColor = "Red"
}

Write-Host "" 
Write-Host "=== Daily Checkpoint Summary ===" -ForegroundColor Green
Write-Host ("Cycles: {0} -> {1} (Δ {2})" -f $before.cycle, $after.cycle, $delta.cycles)
Write-Host ("Equity: {0:N4} -> {1:N4} USDT (Δ {2:+0.0000;-0.0000;0.0000})" -f [double]$before.equity_usdt, [double]$after.equity_usdt, [double]$delta.equity_usdt)
Write-Host ("Cash: {0:N4} -> {1:N4} USDT (Δ {2:+0.0000;-0.0000;0.0000})" -f [double]$before.cash_usdt, [double]$after.cash_usdt, [double]$delta.cash_usdt)
Write-Host ("ROI: {0:+0.0000;-0.0000;0.0000}%" -f $roiPct)
Write-Host ("Realized PnL Δ: {0:+0.0000;-0.0000;0.0000} USDT" -f [double]$delta.realized_profit_usdt)
Write-Host ("Harvested PnL Δ: {0:+0.0000;-0.0000;0.0000} USDT" -f [double]$delta.harvested_profit_usdt)
Write-Host ("Fees Δ: {0:+0.0000;-0.0000;0.0000} USDT" -f [double]$delta.fees_usdt)
Write-Host ("Net After Fees Δ: {0:+0.0000;-0.0000;0.0000} USDT" -f $netAfterFees)
Write-Host ("Status: {0}" -f $status) -ForegroundColor $statusColor
Write-Host ("Report: {0}" -f $reportPath) -ForegroundColor DarkGray

$historyDir = Split-Path -Parent $HistoryCsvPath
if ($historyDir -and -not (Test-Path $historyDir)) {
    New-Item -ItemType Directory -Path $historyDir -Force | Out-Null
}

$row = [pscustomobject]@{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    cycles_before = [int]$before.cycle
    cycles_after = [int]$after.cycle
    cycles_delta = [int]$delta.cycles
    equity_before_usdt = [double]$before.equity_usdt
    equity_after_usdt = [double]$after.equity_usdt
    equity_delta_usdt = [double]$delta.equity_usdt
    roi_pct = [double]$roiPct
    cash_delta_usdt = [double]$delta.cash_usdt
    realized_pnl_delta_usdt = [double]$delta.realized_profit_usdt
    harvested_pnl_delta_usdt = [double]$delta.harvested_profit_usdt
    fees_delta_usdt = [double]$delta.fees_usdt
    net_after_fees_delta_usdt = [double]$netAfterFees
    status = $status
}

$append = Test-Path $HistoryCsvPath
$row | Export-Csv -Path $HistoryCsvPath -NoTypeInformation -Append:$append
Write-Host ("History CSV: {0}" -f $HistoryCsvPath) -ForegroundColor DarkGray
