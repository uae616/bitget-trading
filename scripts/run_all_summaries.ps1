param(
    [int]$Cycles = 50,
    [int]$FastCycleSeconds = 1,
    [int]$WeeklyLookbackDays = 7,
    [int]$MonthlyLookbackDays = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

Write-Host ""
Write-Host "=== Unified Summary Run ===" -ForegroundColor Cyan
Write-Host ("Step 1/3: Daily summary (Cycles={0}, FastCycleSeconds={1})" -f $Cycles, $FastCycleSeconds)
.\scripts\daily_summary.ps1 -Cycles $Cycles -FastCycleSeconds $FastCycleSeconds | Out-Host

Write-Host ""
Write-Host ("Step 2/3: Weekly summary (LookbackDays={0})" -f $WeeklyLookbackDays)
.\scripts\weekly_summary.ps1 -LookbackDays $WeeklyLookbackDays | Out-Host

Write-Host ""
Write-Host ("Step 3/3: Monthly summary (LookbackDays={0})" -f $MonthlyLookbackDays)
.\scripts\monthly_summary.ps1 -LookbackDays $MonthlyLookbackDays | Out-Host

Write-Host ""
Write-Host "Unified summary run complete." -ForegroundColor Green
