Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Administrator\rebalance_bot"

$pythonExe = ".\.venv\Scripts\python.exe"
$lockPath = ".\state\bot.lock"

function Get-LockPid([string]$path) {
	if (-not (Test-Path $path)) { return $null }
	try {
		$pidText = (Get-Content $path -Raw).Trim()
		if ($pidText -match "^\d+$") { return [int]$pidText }
	}
	catch {}
	return $null
}

function Get-PythonCommandLine([int]$procId) {
	try {
		$proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId"
		if ($proc -and $proc.Name -eq "python.exe") {
			return [string]$proc.CommandLine
		}
	}
	catch {}
	return ""
}

function Is-SrcMainProcess([int]$procId) {
	$cmd = Get-PythonCommandLine -procId $procId
	if (-not $cmd) { return $false }
	return ($cmd -match "src\.main")
}

function Get-ChildSrcMainPid([int]$parentPid) {
	$child = Get-CimInstance Win32_Process | Where-Object {
		$_.ParentProcessId -eq $parentPid -and $_.Name -eq "python.exe" -and $_.CommandLine -match "src\.main"
	} | Select-Object -First 1
	if ($child) { return [int]$child.ProcessId }
	return $null
}

if (-not (Test-Path $pythonExe)) {
	throw "Python executable not found: $pythonExe"
}

if (Test-Path $lockPath) {
	$lockPid = Get-LockPid -path $lockPath
	if ($lockPid) {
		if (Is-SrcMainProcess -procId $lockPid) {
			Write-Host "Bot already running (PID: $lockPid)." -ForegroundColor Yellow
			Write-Host "Use .\scripts\stop_bot.ps1 to stop it first." -ForegroundColor Yellow
			exit 0
		}

		Write-Host "Removing stale lock file PID: $lockPid" -ForegroundColor Yellow
		try { Remove-Item $lockPath -Force -ErrorAction Stop } catch {}
	}
}

$proc = Start-Process -FilePath $pythonExe -ArgumentList "-m", "src.main" -WorkingDirectory (Get-Location) -PassThru

Start-Sleep -Seconds 2

$runningPid = $null
$lockPidAfterStart = Get-LockPid -path $lockPath
if ($lockPidAfterStart -and (Is-SrcMainProcess -procId $lockPidAfterStart)) {
	$runningPid = $lockPidAfterStart
}
elseif (Is-SrcMainProcess -procId $proc.Id) {
	$runningPid = $proc.Id
}
else {
	$childPid = Get-ChildSrcMainPid -parentPid $proc.Id
	if ($childPid) { $runningPid = $childPid }
}

if (-not $runningPid) {
	Write-Host "Bot process did not stay running after launch." -ForegroundColor Red
	Write-Host "Run '.\.venv\Scripts\python.exe -m src.main' to inspect foreground logs." -ForegroundColor Yellow
	exit 1
}

Write-Host "Bot started in background. PID: $runningPid" -ForegroundColor Green
Write-Host "Lock file: $lockPath" -ForegroundColor Green
Write-Host "Stop command: .\scripts\stop_bot.ps1" -ForegroundColor Green
