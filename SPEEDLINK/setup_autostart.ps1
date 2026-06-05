param(
    [string]$TaskName = "vJoyFeeder",
    [string]$ScriptDir = $PSScriptRoot,
    [switch]$Remove,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task: $TaskName"
    } else {
        Write-Host "Scheduled task not found: $TaskName"
    }
    exit 0
}

$feeder = Join-Path $ScriptDir "vjoy_feeder.py"
if (!(Test-Path $feeder)) {
    throw "vjoy_feeder.py not found in $ScriptDir"
}

$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (!$pythonw) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (!$python) { throw "python.exe/pythonw.exe not found in PATH" }
    $pythonw = $python
}

$argument = "`"$feeder`" --quiet"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $argument -WorkingDirectory $ScriptDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT15S"
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered scheduled task: $TaskName"
Write-Host "Script: $feeder"
Write-Host "Python: $pythonw"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task: $TaskName"
}
