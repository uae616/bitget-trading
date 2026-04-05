param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("A","B")]
  [string]$ConfigName,

  [int]$Cycles = 500
)

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\Administrator\rebalance_bot"

Write-Host "=== Running experiment $ConfigName for $Cycles cycles ===" -ForegroundColor Cyan

# Swap config in
Copy-Item ".\config_$ConfigName.toml" ".\config.toml" -Force
Write-Host "Config switched: config_$ConfigName.toml -> config.toml" -ForegroundColor Green

# --- Update max_cycles inside EXISTING [bot] section (never add a new [bot]) ---
$cfg = Get-Content .\config.toml -Raw

# If max_cycles already exists anywhere, replace it.
if ($cfg -match "(?m)^\s*max_cycles\s*=\s*\d+\s*$") {
  $cfg = [regex]::Replace($cfg, "(?m)^\s*max_cycles\s*=\s*\d+\s*$", "max_cycles = $Cycles")
}
else {
  # Insert max_cycles right after the FIRST [bot] header
  if ($cfg -match "(?m)^\\[bot\\]\s*$", "[bot]`r`nmax_cycles = $Cycles", 1)
  }
  else {
    throw "config.toml has no [bot] section. Add it to your config_A.toml/config_B.toml."
  }
}

Set-Content .\config.toml $cfg -Encoding UTF8

# Reset baseline state
python -m src.initializer | Out-Host

# Run bot (it should stop itself when cycle reaches max_cycles)
python -m src.main | Out-Host

# Export final state
Copy-Item ".\state\state.json" ".\state\state_$ConfigName.json" -Force
Write-Host "Saved: .\state\state_$ConfigName.json" -ForegroundColor Green
