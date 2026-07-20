# stop.ps1 — Gracefully stop AgentLoop on Windows (PowerShell)
param()

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# Create STOP file to signal graceful halt
New-Item -Force STOP -ItemType File | Out-Null

if (-not (Test-Path "agentloop.pid")) {
    Write-Host "No running agent found."
    exit 0
}

$pidStr = Get-Content "agentloop.pid" -Raw
$pid = [int]($pidStr.Trim())
$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
if (-not $proc) {
    Remove-Item -Force agentloop.pid -ErrorAction SilentlyContinue
    Write-Host "No running agent found (stale pid file cleared)."
    exit 0
}

Write-Host "Stop signal set (STOP). Waiting for pid $pid to exit cleanly..."

Start-Sleep -Seconds 3
$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "Agent halted."
    Remove-Item -Force agentloop.pid -ErrorAction SilentlyContinue
    exit 0
}

# Still alive: try graceful stop
Write-Host "Agent still running, sending Stop-Process..."
Stop-Process -Id $pid -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "Agent halted after Stop-Process."
    Remove-Item -Force agentloop.pid -ErrorAction SilentlyContinue
    exit 0
}

# Force kill
Write-Host "Agent still running after graceful wait; forcing termination."
Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
Remove-Item -Force agentloop.pid -ErrorAction SilentlyContinue
