param(
    [string]$DevicePath,
    [switch]$List,
    [switch]$Off,
    [string]$VidPid = "VID_07B5&PID_0317"
)

$ErrorActionPreference = "Stop"

function Find-HidHideCli {
    $candidates = @(
        "$env:ProgramFiles\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe",
        "$env:ProgramFiles\Nefarius Software Solutions\HidHide\HidHideCLI.exe",
        "$env:ProgramFiles(x86)\Nefarius Software Solutions\HidHide\HidHideCLI.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command HidHideCLI.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "HidHideCLI.exe not found. Install HidHide or add HidHideCLI.exe to PATH."
}

function Require-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated PowerShell (Administrator)."
    }
}

$cli = Find-HidHideCli
Write-Host "HidHideCLI: $cli"

if ($List) {
    & $cli --dev-list
    exit $LASTEXITCODE
}

Require-Admin

if ($Off) {
    & $cli --cloak-off
    Write-Host "HidHide cloak disabled. Physical joystick is visible again."
    exit $LASTEXITCODE
}

if (!$DevicePath) {
    Write-Host "DevicePath was not provided. Devices containing $VidPid:"
    & $cli --dev-list | Select-String -Pattern $VidPid -Context 0,2
    throw "Pass -DevicePath with the exact HID device path, or use -List to inspect devices."
}

$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if ($python) { & $cli --app-reg $python }
if ($pythonw) { & $cli --app-reg $pythonw }

& $cli --dev-hide $DevicePath
& $cli --cloak-on

Write-Host "Physical joystick hidden: $DevicePath"
Write-Host "python/pythonw are whitelisted so vjoy_feeder.py can still read the device."
