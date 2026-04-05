# MT5 Scalper: Safe Live Transition Script
# This script helps you safely transition from dry_run to live trading

param(
    [ValidateSet('check', 'demo', 'live-micro', 'live-small', 'revert')]
    [string]$Mode = 'check'
)

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host "=" * 70 -ForegroundColor Cyan
    Write-Host " $Text" -ForegroundColor Cyan
    Write-Host "=" * 70 -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Text)
    Write-Host "✅ $Text" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Text)
    Write-Host "⚠️  $Text" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Text)
    Write-Host "❌ $Text" -ForegroundColor Red
}

function Check-Prerequisites {
    Write-Header "PRE-FLIGHT CHECKLIST"
    
    $checks = @{
        "config.toml exists" = { Test-Path "config.toml" }
        ".env exists" = { Test-Path ".env" }
        "state/ directory exists" = { Test-Path "state" -PathType Container }
        "logs/ directory exists" = { Test-Path "logs" -PathType Container }
        "MT5 credentials in .env" = { (Get-Content .env) -match "MT5_LOGIN|MT5_PASSWORD|MT5_SERVER" }
        "Python venv active" = { Test-Path ".venv\Scripts\python.exe" }
    }
    
    $allPassed = $true
    foreach ($check in $checks.GetEnumerator()) {
        $result = & $check.Value
        if ($result) {
            Write-Success $check.Key
        } else {
            Write-Error $check.Key
            $allPassed = $false
        }
    }
    
    return $allPassed
}

function Get-ConfigValue {
    param([string]$Key)
    $pattern = "$Key\s*=\s*(.+)"
    $match = Select-String -Path "config.toml" -Pattern $pattern | Select-Object -First 1
    if ($match) {
        return ($match.Matches.Groups[1].Value -replace '["'']', '').Trim()
    }
    return $null
}

function Set-ConfigValue {
    param([string]$Key, [string]$Value)
    $pattern = "$Key\s*=.*"
    $replacement = "$Key = $Value"
    (Get-Content config.toml) -replace $pattern, $replacement | Set-Content config.toml
}

function Set-DryRunMode {
    param([bool]$Enabled)
    $mode = if ($Enabled) { 'true' } else { 'false' }
    Set-ConfigValue "dry_run" $mode
    
    $status = if ($Enabled) { "ENABLED (DRY RUN)" } else { "DISABLED (LIVE TRADING)" }
    Write-Success "dry_run is now: $status"
}

function Show-Config {
    Write-Header "CURRENT CONFIGURATION"
    
    $dryRun = Get-ConfigValue "dry_run"
    $symbols = Get-ConfigValue "symbols"
    $timeframe = Get-ConfigValue "timeframe"
    $posSize = Get-ConfigValue "position_size"
    $maxPos = Get-ConfigValue "max_positions"
    
    Write-Host "Mode:             $dryRun" -ForegroundColor $(if ($dryRun -eq 'true') { 'Green' } else { 'Red' })
    Write-Host "Symbols:          $symbols"
    Write-Host "Timeframe:        $timeframe"
    Write-Host "Position Size:    $posSize lots"
    Write-Host "Max Positions:    $maxPos"
}

function Test-MT5Connection {
    Write-Header "TESTING MT5 CONNECTION"
    Write-Warning "Make sure MetaTrader5 terminal is running and connected..."
    
    $testCode = @'
try:
    import MetaTrader5 as mt5
    if mt5.initialize():
        account_info = mt5.account_info()
        if account_info:
            print(f"✅ Connected to account: {account_info.login}")
            print(f"   Broker: {account_info.server}")
            print(f"   Balance: {account_info.balance:.2f}")
        else:
            print("❌ Could not fetch account info - MT5 may not be logged in")
        mt5.shutdown()
    else:
        print("❌ Could not initialize MT5 - Check if terminal is running")
except ImportError:
    print("❌ MetaTrader5 module not installed. Run: pip install MetaTrader5")
except Exception as e:
    print(f"❌ Error: {e}")
'@
    
    .\.venv\Scripts\python.exe -c $testCode
}

function Transition-ToMode {
    param(
        [string]$Mode,
        [string]$Description,
        [bool]$DryRun,
        [string]$PositionSize,
        [string]$MaxPositions
    )
    
    Write-Header "TRANSITIONING TO: $Description"
    
    Write-Warning "This will modify your config.toml"
    Write-Host "Changes:"
    Write-Host "  dry_run = $($DryRun.ToString().ToLower())"
    Write-Host "  position_size = $PositionSize"
    Write-Host "  max_positions = $MaxPositions"
    Write-Host ""
    
    $confirm = Read-Host "Continue? (yes/no)"
    if ($confirm -ne 'yes') {
        Write-Warning "Cancelled."
        return
    }
    
    # Backup
    Copy-Item config.toml "config.toml.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Write-Success "Backed up config.toml"
    
    # Apply changes
    Set-DryRunMode $DryRun
    Set-ConfigValue "position_size" $PositionSize
    Set-ConfigValue "max_positions" $MaxPositions
    
    Show-Config
    
    Write-Header "NEXT STEPS"
    
    if ($DryRun) {
        Write-Host "1. Open two PowerShell windows:"
        Write-Host "   Window 1: python -m src.mt5_scalper.main"
        Write-Host "   Window 2: python monitor_mt5_live.py"
        Write-Host ""
        Write-Host "2. Watch signals being generated (should see ~5 min)"
        Write-Host ""
        Write-Host "3. Verify no errors in logs/mt5_scalper.log"
    } else {
        Write-Host "1. VERIFY MT5 TERMINAL IS RUNNING AND LOGGED IN"
        Write-Host ""
        Write-Host "2. Open two PowerShell windows:"
        Write-Host "   Window 1: python -m src.mt5_scalper.main"
        Write-Host "   Window 2: python monitor_mt5_live.py"
        Write-Host ""
        Write-Host "3. Watch for real trades opening/closing"
        Write-Host ""
        Write-Host "4. MONITOR CONTINUOUSLY - DO NOT LEAVE UNATTENDED"
        Write-Host ""
        Write-Host "5. If anything goes wrong, press Ctrl+C immediately"
    }
    
    Write-Warning "Read MT5_TRANSITION_GUIDE.md for detailed instructions"
}

# Main menu
switch ($Mode) {
    'check' {
        Write-Header "MT5 SCALPER LIVE TRADING SETUP"
        Write-Host ""
        
        if (-not (Check-Prerequisites)) {
            Write-Error "Fix the issues above before proceeding!"
            exit 1
        }
        
        Write-Header "CONFIGURATION"
        Show-Config
        
        Write-Header "TESTING MT5 CONNECTION"
        Test-MT5Connection
        
        Write-Header "NEXT STEPS"
        Write-Host "To transition to DEMO:           .\scripts\transition_mt5.ps1 -Mode demo"
        Write-Host "To transition to LIVE MICRO:     .\scripts\transition_mt5.ps1 -Mode live-micro"
        Write-Host "To transition to LIVE SMALL:     .\scripts\transition_mt5.ps1 -Mode live-small"
        Write-Host "To revert to dry_run mode:       .\scripts\transition_mt5.ps1 -Mode revert"
    }
    
    'demo' {
        Transition-ToMode `
            -Mode "demo" `
            -Description "DEMO ACCOUNT (0.02 lots, max 2 positions)" `
            -DryRun $true `
            -PositionSize "0.02" `
            -MaxPositions "2"
    }
    
    'live-micro' {
        Write-Warning "YOU ARE ABOUT TO TRADE WITH REAL MONEY"
        Write-Host ""
        $confirm = Read-Host "Type 'I UNDERSTAND' to proceed"
        if ($confirm -ne 'I UNDERSTAND') {
            Write-Warning "Cancelled."
            return
        }
        
        Transition-ToMode `
            -Mode "live-micro" `
            -Description "LIVE ACCOUNT - MICRO SIZE (0.01 lots, max 2 positions)" `
            -DryRun $false `
            -PositionSize "0.01" `
            -MaxPositions "2"
    }
    
    'live-small' {
        Write-Warning "YOU ARE ABOUT TO TRADE WITH REAL MONEY AT INCREASED SIZE"
        Write-Host ""
        $confirm = Read-Host "Type 'I UNDERSTAND' to proceed"
        if ($confirm -ne 'I UNDERSTAND') {
            Write-Warning "Cancelled."
            return
        }
        
        Transition-ToMode `
            -Mode "live-small" `
            -Description "LIVE ACCOUNT - SMALL SIZE (0.05 lots, max 3 positions)" `
            -DryRun $false `
            -PositionSize "0.05" `
            -MaxPositions "3"
    }
    
    'revert' {
        Write-Header "REVERTING TO DRY RUN MODE"
        Set-DryRunMode $true
        Write-Success "Switched back to dry_run = true"
        Write-Warning "Your position will not execute live trades"
    }
}
