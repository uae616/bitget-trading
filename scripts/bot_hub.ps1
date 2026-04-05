param(
    [ValidateSet(
        "list",
        "interactive",
        "bitget-spot",
        "futures",
        "mt5-scanner",
        "mt5-scalper",
        "scanner",
        "dashboard",
        "status-spot",
        "status-futures",
        "stop-spot",
        "backtest-mt5",
        "analyze-mt5-dryrun"
    )]
    [string]$Target = "interactive",

    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$pythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe. Run .\\scripts\\setup_venv.ps1 first."
}

function Show-InteractiveMenu {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║         REBALANCE BOT HUB - INTERACTIVE MENU          ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "BOT ENGINES:" -ForegroundColor Green
    Write-Host "  [1] Bitget Spot Rebalance Bot (src.main_bitget)"
    Write-Host "  [2] Futures Bot (src.main_futures)"
    Write-Host "  [3] MT5 Scalper Bot (src.mt5_scalper.main)"
    Write-Host ""
    Write-Host "SCANNERS & ANALYSIS:" -ForegroundColor Yellow
    Write-Host "  [4] MT5 Selective Scanner (src.mt5_scanner.main)"
    Write-Host "  [5] Unified Exchange Scanner (src.unified_scanner.main)"
    Write-Host "  [6] Unified Scanner Web Dashboard"
    Write-Host ""
    Write-Host "STATUS & CONTROL:" -ForegroundColor Blue
    Write-Host "  [7] Status - Bitget/Binance Spot Bot"
    Write-Host "  [8] Status - Futures Bot"
    Write-Host "  [9] Stop - Bitget/Binance Spot Bot"
    Write-Host ""
    Write-Host "BACKTEST & VALIDATION:" -ForegroundColor Magenta
    Write-Host "  [10] MT5 Backtest Helper"
    Write-Host "  [11] Analyze MT5 Dry-Run State"
    Write-Host ""
    Write-Host "MENU:" -ForegroundColor DarkGray
    Write-Host "  [0] Exit"
    Write-Host ""
    $choice = Read-Host "Enter your choice (0-11)"
    return $choice
}

function Run-SelectedTarget([string]$choice) {
    switch ($choice) {
        "1" { return "bitget-spot" }
        "2" { return "futures" }
        "3" { return "mt5-scalper" }
        "4" { return "mt5-scanner" }
        "5" { return "scanner" }
        "6" { return "dashboard" }
        "7" { return "status-spot" }
        "8" { return "status-futures" }
        "9" { return "stop-spot" }
        "10" { return "backtest-mt5" }
        "11" { return "analyze-mt5-dryrun" }
        "0" { 
            Write-Host "Exiting." -ForegroundColor DarkGray
            exit 0
        }
        default {
            Write-Host "Invalid choice. Try again." -ForegroundColor Red
            return $null
        }
    }
}

function Show-Targets {
    Write-Host ""
    Write-Host "Available bot/tool targets:" -ForegroundColor Cyan
    Write-Host "  list                 Show this list"
    Write-Host "  bitget-spot          Run Bitget spot rebalance bot (src.main_bitget)"
    Write-Host "  futures              Run futures bot (src.main_futures)"
    Write-Host "  mt5-scanner          Run MT5 selective scanner (src.mt5_scanner.main)"
    Write-Host "  mt5-scalper          Run MT5 scalper bot (src.mt5_scalper.main)"
    Write-Host "  scanner              Run unified scanner CLI (src.unified_scanner.main)"
    Write-Host "  dashboard            Run unified scanner web dashboard"
    Write-Host "  status-spot          Show status for src.main bot"
    Write-Host "  status-futures       Show status for futures bot"
    Write-Host "  stop-spot            Stop src.main bot"
    Write-Host "  backtest-mt5         Run MT5 backtest helper (backtest_mt5.py)"
    Write-Host "  analyze-mt5-dryrun   Analyze MT5 dry-run state"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor DarkGray
    Write-Host "  .\\scripts\\bot_hub.ps1 -Target bitget-spot"
    Write-Host "  .\\scripts\\bot_hub.ps1 -Target mt5-scanner -ExtraArgs @('XAUUSD','XAGUSD','--debug')"
    Write-Host "  .\\scripts\\bot_hub.ps1 -Target scanner -ExtraArgs @('--exchange','bitget','--top','20')"
    Write-Host ""
}

$menuItems = @(
    [pscustomobject]@{ Key="1";  Target="bitget-spot";         Label="Run Bitget spot rebalance bot" }
    [pscustomobject]@{ Key="2";  Target="futures";             Label="Run futures bot" }
    [pscustomobject]@{ Key="3";  Target="mt5-scalper";         Label="Run MT5 scalper bot" }
    [pscustomobject]@{ Key="4";  Target="mt5-scanner";         Label="Run MT5 metals/commodities scanner" }
    [pscustomobject]@{ Key="5";  Target="scanner";             Label="Run unified scanner CLI (Bitget/Binance)" }
    [pscustomobject]@{ Key="6";  Target="dashboard";           Label="Run unified scanner web dashboard" }
    [pscustomobject]@{ Key="7";  Target="status-spot";         Label="Show spot bot status" }
    [pscustomobject]@{ Key="8";  Target="status-futures";      Label="Show futures bot status" }
    [pscustomobject]@{ Key="9";  Target="stop-spot";           Label="Stop spot bot" }
    [pscustomobject]@{ Key="10"; Target="backtest-mt5";        Label="Run MT5 backtest" }
    [pscustomobject]@{ Key="11"; Target="analyze-mt5-dryrun";  Label="Analyze MT5 dry-run results" }
    [pscustomobject]@{ Key="0"; Target="quit";                Label="Exit" }
)

if ($Target -eq "interactive") {
    Show-InteractiveMenu
    $choice = Read-Host "Enter your choice (0-11)"
    $Target = Run-SelectedTarget $choice
    if (-not $Target) {
        exit 1
    }
}

switch ($Target) {
    "bitget-spot" {
        & $pythonExe -m src.main_bitget
    }
    "futures" {
        & $pythonExe -m src.main_futures
    }
    "mt5-scanner" {
        if ($ExtraArgs) {
            & $pythonExe -m src.mt5_scanner.main @ExtraArgs
        } else {
            & $pythonExe -m src.mt5_scanner.main
        }
    }
    "mt5-scalper" {
        & $pythonExe -m src.mt5_scalper.main
    }
    "scanner" {
        if ($ExtraArgs) {
            & $pythonExe -m src.unified_scanner.main @ExtraArgs
        } else {
            & $pythonExe -m src.unified_scanner.main
        }
    }
    "dashboard" {
        if ($ExtraArgs) {
            & $pythonExe -m src.unified_scanner.dashboard @ExtraArgs
        } else {
            & $pythonExe -m src.unified_scanner.dashboard
        }
    }
    "status-spot" {
        & .\scripts\status_bot.ps1
    }
    "status-futures" {
        & .\scripts\status_futures_bot.ps1
    }
    "stop-spot" {
        & .\scripts\stop_bot.ps1
    }
    "backtest-mt5" {
        & $pythonExe .\backtest_mt5.py
    }
    "analyze-mt5-dryrun" {
        & $pythonExe .\analyze_mt5_dryrun.py
    }
    default {
        throw "Unknown target: $Target"
    }
}
