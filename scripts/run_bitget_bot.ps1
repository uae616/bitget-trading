# Run Bitget Rebalance Bot (Spot + Futures)
# Usage: .\scripts\run_bitget_bot.ps1

$venv = ".\.venv\Scripts\Activate.ps1"

if (-not (Test-Path $venv)) {
    Write-Host "Virtual environment not found. Run .\scripts\setup_venv.ps1 first."
    exit 1
}

Write-Host "Activating venv..."
& $venv

Write-Host "Starting Bitget Rebalance Bot..."
python -m src.main_bitget
