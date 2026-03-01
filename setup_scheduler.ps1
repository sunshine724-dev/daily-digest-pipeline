# Daily Digest Pipeline Scheduler Setup
# Register a daily task at 22:55 in Windows Task Scheduler

param(
    [string]$PythonPath = "",
    [switch]$Remove
)

$TaskName = "DailyDigestPipeline"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Remove mode
if ($Remove) {
    Write-Host "Removing task '$TaskName'..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Done" -ForegroundColor Green
    exit 0
}

# Detect Python path
if (-not $PythonPath) {
    $VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $PythonPath = $VenvPython
    } else {
        $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}

if (-not $PythonPath -or -not (Test-Path $PythonPath)) {
    Write-Host "Error: Python not found. Use -PythonPath to specify." -ForegroundColor Red
    exit 1
}

Write-Host "Python: $PythonPath" -ForegroundColor Cyan
Write-Host "Project: $ProjectDir" -ForegroundColor Cyan

# Script path
$MainScript = Join-Path $ProjectDir "main.py"

# Task action
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$MainScript`"" `
    -WorkingDirectory $ProjectDir

# Trigger: daily at 22:55
$Trigger = New-ScheduledTaskTrigger -Daily -At "22:55"

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# Overwrite existing task
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "Updating existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Register task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily Digest Pipeline - Update MCP Log at 22:55" `
    -RunLevel Limited

Write-Host ""
Write-Host "Task '$TaskName' registered (daily at 22:55)" -ForegroundColor Green
Write-Host ""
Write-Host "Check:  Get-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "Run:    Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host 'Remove: .\setup_scheduler.ps1 -Remove' -ForegroundColor Gray
