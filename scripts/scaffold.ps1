$proj = (Get-Location).Path

$dirs = @(
  "state","logs","scripts",
  "src","src\core","src\data","src\binance","src\engine","src\utils"
)

foreach ($d in $dirs) {
  $p = Join-Path $proj $d
  if (!(Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

$files = @(
  "README.md","requirements.txt","config.toml",".env.example",".gitignore",
  "state\state.json",
  "src\main.py",
  "src\core\logger.py","src\core\persistence.py","src\core\settings.py","src\core\clock.py","src\core\errors.py",
  "src\data\price_cache.py","src\data\spot_filters.py","src\data\convert_limits.py",
  "src\binance\rest_client.py","src\binance\spot_api.py","src\binance\convert_api.py",
  "src\engine\momentum.py","src\engine\strategy.py","src\engine\execution.py",
  "src\engine\accounting.py","src\engine\take_profit.py","src\engine\dip_buy.py","src\engine\reconcile.py",
  "src\utils\math_utils.py","src\utils\symbols.py",
  "scripts\setup_venv.ps1","scripts\run_bot.ps1"
)

foreach ($f in $files) {
  $p = Join-Path $proj $f
  if (!(Test-Path $p)) { New-Item -ItemType File -Path $p | Out-Null }
}

Write-Host "✅ Scaffold created in: $proj" -ForegroundColor Green
