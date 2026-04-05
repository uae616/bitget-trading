param(
    [int]$LookbackDays = 30,
    [string]$HistoryCsvPath = ".\state\daily_summary_history.csv",
    [switch]$All,
    [string]$MonthlyHistoryCsvPath = ".\state\monthly_summary_history.csv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

if (-not (Test-Path $HistoryCsvPath)) {
    throw "History CSV not found: $HistoryCsvPath"
}

$rows = Import-Csv -Path $HistoryCsvPath
if (-not $rows -or $rows.Count -eq 0) {
    Write-Host ("No history rows yet in {0}. Run .\scripts\daily_summary.ps1 first." -f $HistoryCsvPath) -ForegroundColor Yellow
    return
}

$parsed = @()
foreach ($row in $rows) {
    $tsRaw = [string]$row.timestamp_utc
    if ([string]::IsNullOrWhiteSpace($tsRaw)) {
        continue
    }

    try {
        $ts = [datetime]::Parse($tsRaw).ToUniversalTime()
    }
    catch {
        continue
    }

    $parsed += [pscustomobject]@{
        timestamp_utc = $ts
        status = [string]$row.status
        roi_pct = [double]$row.roi_pct
        net_after_fees_delta_usdt = [double]$row.net_after_fees_delta_usdt
        equity_delta_usdt = [double]$row.equity_delta_usdt
        fees_delta_usdt = [double]$row.fees_delta_usdt
    }
}

if (-not $parsed -or $parsed.Count -eq 0) {
    Write-Host ("No valid records found in {0}." -f $HistoryCsvPath) -ForegroundColor Yellow
    return
}

$nowUtc = (Get-Date).ToUniversalTime()
$windowStart = $nowUtc.AddDays(-1 * [math]::Abs($LookbackDays))

$selected = if ($All) {
    $parsed
}
else {
    $parsed | Where-Object { $_.timestamp_utc -ge $windowStart }
}

if (-not $selected -or $selected.Count -eq 0) {
    if ($All) {
        Write-Host "No rows available in full-history mode." -ForegroundColor Yellow
        return
    }
    Write-Host ("No rows found in the last {0} days." -f $LookbackDays) -ForegroundColor Yellow
    return
}

$totalRuns = @($selected).Count
$wins = @($selected | Where-Object { $_.status -eq "PROFIT" }).Count
$losses = @($selected | Where-Object { $_.status -eq "LOSS" }).Count
$flats = @($selected | Where-Object { $_.status -eq "FLAT" }).Count

$decisive = $wins + $losses
$winRate = if ($decisive -gt 0) { ($wins / $decisive) * 100.0 } else { 0.0 }
$avgRoi = ($selected | Measure-Object -Property roi_pct -Average).Average
$totalNet = ($selected | Measure-Object -Property net_after_fees_delta_usdt -Sum).Sum
$totalFees = ($selected | Measure-Object -Property fees_delta_usdt -Sum).Sum
$totalEquityDelta = ($selected | Measure-Object -Property equity_delta_usdt -Sum).Sum

$firstTs = ($selected | Sort-Object timestamp_utc | Select-Object -First 1).timestamp_utc
$lastTs = ($selected | Sort-Object timestamp_utc | Select-Object -Last 1).timestamp_utc

Write-Host ""
Write-Host "=== Monthly Performance Summary ===" -ForegroundColor Green
if ($All) {
    Write-Host ("Window: ALL ({0} -> {1})" -f $firstTs.ToString("yyyy-MM-dd HH:mm:ss"), $lastTs.ToString("yyyy-MM-dd HH:mm:ss"))
}
else {
    Write-Host ("Window: Last {0} days ({1} -> {2})" -f $LookbackDays, $firstTs.ToString("yyyy-MM-dd HH:mm:ss"), $lastTs.ToString("yyyy-MM-dd HH:mm:ss"))
}
Write-Host ("Runs: {0} | PROFIT={1} LOSS={2} FLAT={3}" -f $totalRuns, $wins, $losses, $flats)
Write-Host ("Win Rate (PROFIT vs LOSS): {0:N2}%" -f $winRate)
Write-Host ("Average ROI: {0:+0.0000;-0.0000;0.0000}%" -f [double]$avgRoi)
Write-Host ("Total Net After Fees: {0:+0.0000;-0.0000;0.0000} USDT" -f [double]$totalNet)
Write-Host ("Total Equity Δ: {0:+0.0000;-0.0000;0.0000} USDT" -f [double]$totalEquityDelta)
Write-Host ("Total Fees Δ: {0:+0.0000;-0.0000;0.0000} USDT" -f [double]$totalFees)
Write-Host ("History CSV: {0}" -f $HistoryCsvPath) -ForegroundColor DarkGray

$monthlyHistoryDir = Split-Path -Parent $MonthlyHistoryCsvPath
if ($monthlyHistoryDir -and -not (Test-Path $monthlyHistoryDir)) {
    New-Item -ItemType Directory -Path $monthlyHistoryDir -Force | Out-Null
}

$windowMode = if ($All) { "ALL" } else { "LOOKBACK_DAYS" }
$monthlyRow = [pscustomobject]@{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    window_mode = $windowMode
    lookback_days = [int]$LookbackDays
    window_start_utc = $firstTs.ToString("yyyy-MM-ddTHH:mm:ssZ")
    window_end_utc = $lastTs.ToString("yyyy-MM-ddTHH:mm:ssZ")
    runs = [int]$totalRuns
    wins = [int]$wins
    losses = [int]$losses
    flats = [int]$flats
    win_rate_pct = [double]$winRate
    average_roi_pct = [double]$avgRoi
    total_net_after_fees_usdt = [double]$totalNet
    total_equity_delta_usdt = [double]$totalEquityDelta
    total_fees_delta_usdt = [double]$totalFees
}

$monthlyAppend = Test-Path $MonthlyHistoryCsvPath
$monthlyRow | Export-Csv -Path $MonthlyHistoryCsvPath -NoTypeInformation -Append:$monthlyAppend
Write-Host ("Monthly History CSV: {0}" -f $MonthlyHistoryCsvPath) -ForegroundColor DarkGray
