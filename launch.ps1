# launch.ps1 — Turnkey launcher for AgentLoop on Windows (PowerShell)
# Usage: .\launch.ps1   (runs in background, safe, idempotent)
param()

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# 1) check direct mode key
$MODE = if ($env:AGENT_MODE) { $env:AGENT_MODE.ToLower() } else { "cli" }
if ($MODE -eq "direct" -and -not (Test-Path ".env") -and [string]::IsNullOrEmpty($env:KILO_API_KEY) -and [string]::IsNullOrEmpty($env:KILOCODE_API_KEY)) {
    Write-Host "==================================================================="
    Write-Host " direct mode needs a key. Either set AGENT_MODE=cli (default, bring"
    Write-Host " your own agent CLI like opencode), or put"
    Write-Host " KILO_API_KEY=sk-... in $ROOT\.env for direct mode."
    Write-Host "==================================================================="
    exit 1
}

# 2) don't start a second copy
if (Test-Path "agentloop.pid") {
    $pidStr = Get-Content "agentloop.pid" -Raw
    $pidNum = [int]($pidStr.Trim())
    $proc = Get-Process -Id $pidNum -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Already running (pid $pidNum). Tail: Get-Content agentloop.log -Wait"
        exit 0
    }
}

# 3) ensure sandbox exists and is a git repo
if (-not (Test-Path "sandbox")) {
    New-Item -ItemType Directory -Path "sandbox" | Out-Null
}
if (-not (Test-Path "sandbox\.git")) {
    Push-Location "sandbox"
    git init -q 2>$null
    git config user.email "agentloop@local" 2>$null
    git config user.name "agentloop" 2>$null
    Pop-Location
}

# 4) clear any stale STOP signal and launch
Remove-Item -Force STOP -ErrorAction SilentlyContinue

# Use Start-Process to run agentloop.py in the background
# The process ID is captured so stop.ps1 and status can find it
$logFile = Join-Path $ROOT "agentloop.log"
$process = Start-Process -FilePath "python" -ArgumentList "agentloop.py" `
    -WorkingDirectory $ROOT `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError $logFile `
    -NoNewWindow -PassThru

$process.Id | Out-File -FilePath "agentloop.pid" -Encoding ASCII
Write-Host "Launched pid $($process.Id). Mode=$MODE. Logs: Get-Content $ROOT\agentloop.log -Wait  | Stop: .\stop.ps1"
