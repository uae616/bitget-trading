param(
    [int]$IntervalSeconds = 30,
    [switch]$Once,
    [int]$NearMissCount = 5,
    [string]$ExternalScannerPath = "C:\Users\Administrator\3D Objects\WORKSPACE",
    [string]$ExternalSignalsCsv = "",
    [string]$ExternalSignalsPattern = "detailed_signals_*.csv",
    [int]$ExternalTopN = 5,
    [int]$ExternalFreshMaxMinutes = 10,
    [switch]$AllowStaleExternalSignals,
    [switch]$StartExternalScanner
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$statePath = ".\state\state.json"
$logPath = ".\logs\bot.log"

function Resolve-ExternalSignalsCsvPath([string]$scannerPath, [string]$explicitCsv, [string]$pattern) {
    if ($explicitCsv -and (Test-Path $explicitCsv)) {
        return $explicitCsv
    }

    $outputDir = Join-Path $scannerPath "output"
    if (Test-Path $outputDir) {
        $latest = Get-ChildItem -Path $outputDir -Filter $pattern -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($latest) {
            return $latest.FullName
        }
    }

    if ($explicitCsv) {
        return $explicitCsv
    }
    return (Join-Path $scannerPath "signals.csv")
}

$userProvidedExternalCsv = -not [string]::IsNullOrWhiteSpace($ExternalSignalsCsv)
$ExternalSignalsCsv = Resolve-ExternalSignalsCsvPath -scannerPath $ExternalScannerPath -explicitCsv $ExternalSignalsCsv -pattern $ExternalSignalsPattern

function Get-LatestCycleLine([string[]]$tailLines) {
    $cycleMatches = $tailLines | Select-String -Pattern "Cycle \d+ running"
    if ($cycleMatches) {
        return $cycleMatches[-1].Line
    }
    return $null
}

function Get-HeartbeatAgeSeconds([string]$line) {
    if (-not $line) { return $null }
    $m = [regex]::Match($line, "^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]")
    if (-not $m.Success) { return $null }
    try {
        $ts = [datetime]::ParseExact($m.Groups[1].Value, "yyyy-MM-dd HH:mm:ss", $null)
        return [int]([datetime]::Now - $ts).TotalSeconds
    }
    catch {
        return $null
    }
}

function Get-NearMisses([string[]]$tailLines, [int]$maxCount) {
    $items = @()

    foreach ($line in $tailLines) {
        $mBuffer = [regex]::Match($line, "\[NO_BUY\]\[BUFFER\].*spendable=(?<spend>[-0-9\.]+)\s*<\s*min_buy=(?<min>[-0-9\.]+)")
        if ($mBuffer.Success) {
            $spend = [double]$mBuffer.Groups["spend"].Value
            $minBuy = [double]$mBuffer.Groups["min"].Value
            $score = 0.0
            if ($minBuy -gt 0) {
                $score = [math]::Max(0.0, [math]::Min(1.0, $spend / $minBuy))
            }
            $items += [pscustomobject]@{
                score = $score
                type = "BUFFER"
                detail = "spendable=$([math]::Round($spend,2)) / min_buy=$([math]::Round($minBuy,2))"
            }
            continue
        }

        $mFloorRot = [regex]::Match($line, "\[NO_BUY\]\[FLOOR\]\[ROTATION\]\s+coin=(?<coin>[A-Z]+)\s+z=(?<z>[-0-9\.]+)\s*<\s*floor_z=(?<f>[-0-9\.]+)")
        if ($mFloorRot.Success) {
            $coin = $mFloorRot.Groups["coin"].Value
            $z = [double]$mFloorRot.Groups["z"].Value
            $f = [double]$mFloorRot.Groups["f"].Value
            $gap = [math]::Max(0.0, $f - $z)
            $score = [math]::Max(0.0, [math]::Min(1.0, 1.0 - ($gap / 1.0)))
            $items += [pscustomobject]@{
                score = $score
                type = "FLOOR_ROT"
                detail = "$coin z=$([math]::Round($z,2)) vs floor=$([math]::Round($f,2))"
            }
            continue
        }

        $mFloorTrend = [regex]::Match($line, "\[NO_BUY\]\[FLOOR\]\[TREND\]\s+top=(?<coin>[A-Z]+)\s+top_z=(?<z>[-0-9\.]+)\s*<\s*floor_z=(?<f>[-0-9\.]+)")
        if ($mFloorTrend.Success) {
            $coin = $mFloorTrend.Groups["coin"].Value
            $z = [double]$mFloorTrend.Groups["z"].Value
            $f = [double]$mFloorTrend.Groups["f"].Value
            $gap = [math]::Max(0.0, $f - $z)
            $score = [math]::Max(0.0, [math]::Min(1.0, 1.0 - ($gap / 1.0)))
            $items += [pscustomobject]@{
                score = $score
                type = "FLOOR_TREND"
                detail = "$coin top_z=$([math]::Round($z,2)) vs floor=$([math]::Round($f,2))"
            }
            continue
        }

        $mRegime = [regex]::Match($line, "\[TRACE\]\[REGIME\].*top=(?<coin>[A-Z]+)\s+top_z=(?<top>[-0-9\.]+).*gap=(?<gap>[-0-9\.]+).*trend_entry_z=(?<entry>[-0-9\.]+)\s+dominance_gap=(?<dom>[-0-9\.]+)\s+trend_mode=False")
        if ($mRegime.Success) {
            $coin = $mRegime.Groups["coin"].Value
            $top = [double]$mRegime.Groups["top"].Value
            $gap = [double]$mRegime.Groups["gap"].Value
            $entry = [double]$mRegime.Groups["entry"].Value
            $dom = [double]$mRegime.Groups["dom"].Value

            $zPart = if ($entry -gt 0) { [math]::Max(0.0, [math]::Min(1.0, $top / $entry)) } else { 0.0 }
            $gapPart = if ($dom -gt 0) { [math]::Max(0.0, [math]::Min(1.0, $gap / $dom)) } else { 0.0 }
            $score = [math]::Min($zPart, $gapPart)

            $items += [pscustomobject]@{
                score = $score
                type = "TREND_REGIME"
                detail = "$coin top_z=$([math]::Round($top,2))/$([math]::Round($entry,2)), gap=$([math]::Round($gap,2))/$([math]::Round($dom,2))"
            }
            continue
        }
    }

    if ($items.Count -eq 0) { return @() }
    return $items | Sort-Object score -Descending | Select-Object -First $maxCount
}

function Get-ColumnName([object]$row, [string[]]$candidates) {
    if (-not $row) { return $null }
    $names = @($row.PSObject.Properties | ForEach-Object { $_.Name })
    foreach ($cand in $candidates) {
        foreach ($n in $names) {
            if ($n.ToLower() -eq $cand.ToLower()) {
                return $n
            }
        }
    }
    return $null
}

function To-DoubleSafe([object]$v) {
    try {
        if ($null -eq $v) { return $null }
        $s = [string]$v
        if (-not $s) { return $null }
        return [double]$s
    }
    catch {
        return $null
    }
}

function Get-ExternalSignals([string]$csvPath, [int]$topN) {
    if (-not (Test-Path $csvPath)) {
        return @()
    }

    try {
        $rows = Import-Csv -Path $csvPath
    }
    catch {
        return @()
    }

    if (-not $rows -or $rows.Count -eq 0) {
        return @()
    }

    $first = $rows[0]
    $symbolCol = Get-ColumnName -row $first -candidates @("symbol", "coin", "asset", "pair", "ticker")
    $signalCol = Get-ColumnName -row $first -candidates @("signal", "action", "side", "decision")
    $scoreCol = Get-ColumnName -row $first -candidates @("score", "priority", "rank_score", "confidence", "signal_score")
    $slCol = Get-ColumnName -row $first -candidates @("sl", "stop_loss", "stoploss", "stop", "sl_price")
    $tpCol = Get-ColumnName -row $first -candidates @("tp", "take_profit", "takeprofit", "target", "tp_price")

    $mapped = @()
    foreach ($r in $rows) {
        $symbol = if ($symbolCol) { [string]$r.$symbolCol } else { "n/a" }
        $signal = if ($signalCol) { [string]$r.$signalCol } else { "n/a" }
        $score = if ($scoreCol) { To-DoubleSafe $r.$scoreCol } else { $null }
        $sl = if ($slCol) { [string]$r.$slCol } else { "" }
        $tp = if ($tpCol) { [string]$r.$tpCol } else { "" }

        $mapped += [pscustomobject]@{
            symbol = $symbol
            signal = $signal
            score = $score
            sl = $sl
            tp = $tp
        }
    }

    if ($scoreCol) {
        return $mapped | Sort-Object @{Expression = { if ($null -eq $_.score) { -1e99 } else { $_.score } }} -Descending | Select-Object -First $topN
    }

    return $mapped | Select-Object -First $topN
}

function Start-ExternalScannerIfNeeded([string]$scannerPath) {
    $existing = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -match "main\.py" -and $_.CommandLine -match "--live" -and $_.CommandLine -match [regex]::Escape($scannerPath)
    } | Select-Object -First 1

    if ($existing) {
        Write-Host "External scanner already running (PID: $($existing.ProcessId))." -ForegroundColor DarkGray
        return
    }

    if (-not (Test-Path $scannerPath)) {
        Write-Host "External scanner path not found: $scannerPath" -ForegroundColor Yellow
        return
    }

    Start-Process -FilePath "python" -ArgumentList "main.py", "--live" -WorkingDirectory $scannerPath | Out-Null
    Write-Host "Started external scanner: python main.py --live" -ForegroundColor Green
}

function Get-ExternalCsvMeta([string]$csvPath, [int]$freshMaxMinutes) {
    if (-not (Test-Path $csvPath)) {
        return [pscustomobject]@{
            exists = $false
            path = $csvPath
            ageMinutes = $null
            isFresh = $false
            lastWrite = $null
        }
    }

    $item = Get-Item $csvPath
    $age = [math]::Round(([datetime]::Now - $item.LastWriteTime).TotalMinutes, 2)
    $isFresh = $age -le $freshMaxMinutes

    return [pscustomobject]@{
        exists = $true
        path = $csvPath
        ageMinutes = $age
        isFresh = $isFresh
        lastWrite = $item.LastWriteTime
    }
}

function Get-EquityEstimate([pscustomobject]$state) {
    $cash = [double]($state.cash_usdt)
    $equity = $cash

    $positions = $state.positions
    if (-not $positions) { return $equity }

    foreach ($prop in $positions.PSObject.Properties) {
        $coin = $prop.Name
        $pos = $prop.Value
        $amt = [double]($pos.amount)
        $avg = [double]($pos.avg_price)
        $equity += ($amt * $avg)
    }

    return $equity
}

function Print-Snapshot {
    if (-not (Test-Path $statePath)) {
        Write-Host "state.json not found." -ForegroundColor Yellow
        return
    }

    $state = Get-Content $statePath -Raw | ConvertFrom-Json
    $cycle = [int]$state.meta.cycle
    $cash = [double]$state.cash_usdt
    $realized = [double]$state.pnl.realized_profit_usdt
    $harvested = [double]$state.pnl.harvested_profit_usdt
    $fees = [double]$state.pnl.fees_usdt
    $netRealized = $realized + $harvested - $fees
    $equity = Get-EquityEstimate -state $state

    $heartbeatAge = $null
    $nearMisses = @()
    $externalMeta = Get-ExternalCsvMeta -csvPath $ExternalSignalsCsv -freshMaxMinutes $ExternalFreshMaxMinutes
    $externalSignals = @()
    if ($externalMeta.exists -and ($externalMeta.isFresh -or $AllowStaleExternalSignals)) {
        $externalSignals = @(Get-ExternalSignals -csvPath $ExternalSignalsCsv -topN $ExternalTopN)
    }
    if (Test-Path $logPath) {
        $tail = Get-Content $logPath -Tail 200
        $cycleLine = Get-LatestCycleLine -tailLines $tail
        $heartbeatAge = Get-HeartbeatAgeSeconds -line $cycleLine
        $nearMisses = Get-NearMisses -tailLines $tail -maxCount $NearMissCount
    }

    $heartbeatText = if ($heartbeatAge -ne $null) { "${heartbeatAge}s" } else { "unknown" }
    $status = if ($heartbeatAge -ne $null -and $heartbeatAge -le 120) { "RUNNING" } else { "STALE/UNKNOWN" }

    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$now] Status=$status Heartbeat=$heartbeatText Cycle=$cycle Cash=$([math]::Round($cash,2)) EquityEst=$([math]::Round($equity,2)) NetRealized=$([math]::Round($netRealized,4))" -ForegroundColor Cyan

    $nearMissList = @($nearMisses)
    if ($nearMissList.Count -gt 0) {
        Write-Host "Near Misses (most important first):" -ForegroundColor DarkYellow
        $rank = 1
        foreach ($nm in $nearMissList) {
            $pct = [math]::Round($nm.score * 100.0, 1)
            Write-Host ("  {0}. [{1}%] {2} - {3}" -f $rank, $pct, $nm.type, $nm.detail) -ForegroundColor DarkYellow
            $rank++
        }
    }
    else {
        Write-Host "Near Misses: none found in recent logs." -ForegroundColor DarkGray
    }

    if (-not $externalMeta.exists) {
        Write-Host ("External Signals: none (CSV not found at {0})" -f $externalMeta.path) -ForegroundColor DarkGray
    }
    elseif (-not $externalMeta.isFresh -and -not $AllowStaleExternalSignals) {
        Write-Host ("External Signals: stale file ignored (age={0} min, max={1} min)" -f $externalMeta.ageMinutes, $ExternalFreshMaxMinutes) -ForegroundColor Yellow
        Write-Host ("CSV: {0} (last write: {1})" -f $externalMeta.path, $externalMeta.lastWrite) -ForegroundColor DarkGray
    }
    elseif ($externalSignals.Count -gt 0) {
        Write-Host "External Signals (most important first):" -ForegroundColor Green
        $idx = 1
        foreach ($sig in $externalSignals) {
            $scoreText = if ($null -ne $sig.score) { [math]::Round([double]$sig.score, 4) } else { "n/a" }
            $slText = if ($sig.sl) { $sig.sl } else { "n/a" }
            $tpText = if ($sig.tp) { $sig.tp } else { "n/a" }
            Write-Host ("  {0}. {1} {2} score={3} SL={4} TP={5}" -f $idx, $sig.symbol, $sig.signal, $scoreText, $slText, $tpText) -ForegroundColor Green
            $idx++
        }
        Write-Host ("CSV: {0}" -f $ExternalSignalsCsv) -ForegroundColor DarkGray
    }
    else {
        $freshness = if ($externalMeta.isFresh) { "fresh" } else { "stale" }
        Write-Host ("External Signals: none (CSV {0}/empty at {1})" -f $freshness, $ExternalSignalsCsv) -ForegroundColor DarkGray
    }
}

if ($StartExternalScanner) {
    Start-ExternalScannerIfNeeded -scannerPath $ExternalScannerPath
}

if ($Once) {
    Print-Snapshot
    exit 0
}

while ($true) {
    $explicitForRefresh = if ($userProvidedExternalCsv) { $ExternalSignalsCsv } else { "" }
    $ExternalSignalsCsv = Resolve-ExternalSignalsCsvPath -scannerPath $ExternalScannerPath -explicitCsv $explicitForRefresh -pattern $ExternalSignalsPattern
    Print-Snapshot
    Start-Sleep -Seconds $IntervalSeconds
}
