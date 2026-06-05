<#
.SYNOPSIS
    Find and optionally remove Windows registry entries related to a USB game controller VID/PID.

.DESCRIPTION
    Guarded cleanup tool for cases where Windows keeps stale registry state for a device.

    Default target is Speedlink Black Widow SL-6640 VID_07B5&PID_0317, but another VID/PID can be passed.

    Safety rules:
      - scan-only by default;
      - deletion requires -Apply;
      - registry backup is created before deletion unless -NoBackup is passed;
      - HKLM writes require elevated PowerShell;
      - low-level Enum branches are NOT scanned/deleted unless -IncludeEnum is passed;
      - default matching uses the full VID_XXXX&PID_YYYY pair, not VID-only/PID-only.

.EXAMPLES
    # Scan only
    powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1

    # Scan and write report
    powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1 -ReportPath .\registry_cleanup_report.txt

    # Delete matched non-Enum keys/values after backup
    powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1 -Apply

    # Include low-level Enum branches too (advanced; run as Administrator)
    powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1 -Apply -IncludeEnum
#>

param(
    [string]$Vid = "07B5",
    [string]$Pid = "0317",
    [switch]$Apply,
    [switch]$IncludeEnum,
    [switch]$NoBackup,
    [switch]$BroadMatch,
    [string]$BackupDir = (Join-Path $PSScriptRoot "registry_backups"),
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

$Vid = $Vid.Trim().ToUpper().Replace("0X", "")
$Pid = $Pid.Trim().ToUpper().Replace("0X", "")
$VidPid = "VID_${Vid}&PID_${Pid}"
$Needles = @($VidPid)
if ($BroadMatch) {
    # Advanced mode: may match other devices from the same vendor/product family.
    $Needles += @("VID_${Vid}", "PID_${Pid}")
}

function Write-Line {
    param([string]$Text = "")
    Write-Host $Text
    if ($script:ReportPath) {
        Add-Content -Path $script:ReportPath -Value $Text -Encoding UTF8
    }
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Convert-ToRegExePath {
    param([string]$PsPath)
    $p = $PsPath
    $p = $p -replace '^Microsoft\.PowerShell\.Core\\Registry::', ''
    $p = $p -replace '^Registry::', ''
    $p = $p -replace '^HKEY_CURRENT_USER', 'HKCU'
    $p = $p -replace '^HKEY_LOCAL_MACHINE', 'HKLM'
    $p = $p -replace '^HKEY_CLASSES_ROOT', 'HKCR'
    $p = $p -replace '^HKEY_USERS', 'HKU'
    $p = $p -replace '^HKEY_CURRENT_CONFIG', 'HKCC'
    return $p
}

function Test-MatchText {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $false }
    $upper = $Text.ToUpperInvariant()
    foreach ($needle in $Needles) {
        if ($upper.Contains($needle)) { return $true }
    }
    return $false
}

function Add-UniqueKey {
    param(
        [hashtable]$Map,
        [string]$Path,
        [string]$Reason,
        [bool]$Protected = $false
    )
    if (-not $Map.ContainsKey($Path)) {
        $Map[$Path] = [ordered]@{
            Path = $Path
            Reasons = New-Object System.Collections.Generic.List[string]
            Protected = $Protected
        }
    }
    $Map[$Path].Reasons.Add($Reason) | Out-Null
    if ($Protected) { $Map[$Path].Protected = $true }
}

function Export-KeyBackup {
    param([string]$PsPath)
    if ($NoBackup) { return $null }
    if (!(Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }
    $regPath = Convert-ToRegExePath $PsPath
    $safeName = ($regPath -replace '[\\/:*?"<>| ]+', '_')
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $out = Join-Path $BackupDir "$stamp`_$safeName.reg"
    & reg.exe export $regPath $out /y | Out-Null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) { return $out }
    return $null
}

function Remove-KeySafe {
    param([string]$PsPath)
    $backup = Export-KeyBackup $PsPath
    if ($backup) { Write-Line "  backup: $backup" }
    Remove-Item -LiteralPath $PsPath -Recurse -Force
}

function Scan-RegistryRoot {
    param(
        [string]$Root,
        [hashtable]$KeyMatches,
        [System.Collections.Generic.List[object]]$ValueMatches,
        [bool]$ProtectedRoot = $false
    )

    if (!(Test-Path $Root)) { return }

    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Root)

    while ($stack.Count -gt 0) {
        $path = $stack.Pop()
        $protected = $ProtectedRoot -or ($path -match '\\Enum\\')

        if (Test-MatchText $path) {
            Add-UniqueKey -Map $KeyMatches -Path $path -Reason "path contains target id" -Protected:$protected
        }

        try {
            $item = Get-Item -LiteralPath $path -ErrorAction Stop
            foreach ($name in $item.GetValueNames()) {
                $value = $item.GetValue($name, $null, 'DoNotExpandEnvironmentNames')
                $valueText = if ($null -eq $value) {
                    ""
                } elseif ($value -is [byte[]]) {
                    [BitConverter]::ToString($value)
                } elseif ($value -is [array]) {
                    ($value -join ';')
                } else {
                    [string]$value
                }
                if ((Test-MatchText $name) -or (Test-MatchText $valueText)) {
                    $ValueMatches.Add([ordered]@{ Path = $path; Name = $name; Value = $valueText; Protected = $protected }) | Out-Null
                    if (Test-MatchText $path) {
                        Add-UniqueKey -Map $KeyMatches -Path $path -Reason "value also contains target id" -Protected:$protected
                    }
                }
            }
        } catch {
            # Some keys are locked; skip values but continue scan.
        }

        try {
            foreach ($child in Get-ChildItem -LiteralPath $path -ErrorAction Stop) {
                $stack.Push($child.PSPath)
            }
        } catch {
            # Some keys are locked; skip children.
        }
    }
}

if ($ReportPath) {
    $parent = Split-Path -Parent $ReportPath
    if ($parent -and !(Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $script:ReportPath = $ReportPath
    Set-Content -Path $script:ReportPath -Value "" -Encoding UTF8
} else {
    $script:ReportPath = ""
}

Write-Line "Registry cleanup target: $VidPid"
Write-Line ("Mode: " + $(if ($Apply) { "APPLY (delete)" } else { "SCAN ONLY" }))
Write-Line "Include Enum branches: $IncludeEnum"
Write-Line "Broad match: $BroadMatch"
Write-Line "Backup enabled: $(-not $NoBackup)"
Write-Line ""

$roots = @(
    "Registry::HKEY_CURRENT_USER\System\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick",
    "Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick",
    "Registry::HKEY_CURRENT_USER\System\CurrentControlSet\Control\MediaProperties\PrivateProperties\DirectInput",
    "Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\MediaProperties\PrivateProperties\DirectInput",
    "Registry::HKEY_CURRENT_USER\Software",
    "Registry::HKEY_LOCAL_MACHINE\SOFTWARE"
)

if ($IncludeEnum) {
    $roots += @(
        "Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\HID",
        "Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\USB"
    )
}

$keyMatches = @{}
$valueMatches = New-Object System.Collections.Generic.List[object]

foreach ($root in $roots) {
    Write-Line "Scanning: $root"
    Scan-RegistryRoot -Root $root -KeyMatches $keyMatches -ValueMatches $valueMatches -ProtectedRoot:($root -match '\\Enum\\')
}

Write-Line ""
Write-Line "Matched keys: $($keyMatches.Count)"
foreach ($entry in ($keyMatches.Values | Sort-Object Path)) {
    $mark = if ($entry.Protected) { " [ENUM/PROTECTED]" } else { "" }
    Write-Line ("KEY{0}: {1}" -f $mark, $entry.Path)
    foreach ($reason in $entry.Reasons) { Write-Line "  - $reason" }
}

Write-Line ""
Write-Line "Matched values: $($valueMatches.Count)"
foreach ($entry in ($valueMatches | Sort-Object Path, Name)) {
    $mark = if ($entry.Protected) { " [ENUM/PROTECTED]" } else { "" }
    Write-Line ("VALUE{0}: {1} :: {2} = {3}" -f $mark, $entry.Path, $entry.Name, $entry.Value)
}

if (-not $Apply) {
    Write-Line ""
    Write-Line "Scan only. Nothing was deleted. Re-run with -Apply to delete matched non-Enum keys and matched values."
    Write-Line "Use -IncludeEnum only if you intentionally want to include low-level device enumeration branches."
    Write-Line "Use -BroadMatch only if full VID/PID matching did not find everything you expect."
    exit 0
}

if (-not (Test-Admin)) {
    throw "-Apply requires elevated PowerShell (Run as Administrator)."
}

Write-Line ""
Write-Line "Deleting matched registry entries..."

foreach ($entry in ($keyMatches.Values | Sort-Object { $_.Path.Length } -Descending)) {
    if ($entry.Protected -and -not $IncludeEnum) { continue }
    if ($entry.Protected -and $IncludeEnum) {
        Write-Line "PROTECTED DELETE ATTEMPT: $($entry.Path)"
        Write-Line "  Note: Enum keys may still fail without SYSTEM/TrustedInstaller permissions."
    } else {
        Write-Line "DELETE KEY: $($entry.Path)"
    }
    try {
        Remove-KeySafe $entry.Path
    } catch {
        Write-Line "  FAILED: $($_.Exception.Message)"
    }
}

foreach ($entry in $valueMatches) {
    if ($keyMatches.ContainsKey($entry.Path)) { continue } # parent key already removed or attempted
    if ($entry.Protected -and -not $IncludeEnum) { continue }
    Write-Line "DELETE VALUE: $($entry.Path) :: $($entry.Name)"
    try {
        if (-not $NoBackup) { [void](Export-KeyBackup $entry.Path) }
        Remove-ItemProperty -LiteralPath $entry.Path -Name $entry.Name -Force
    } catch {
        Write-Line "  FAILED: $($_.Exception.Message)"
    }
}

Write-Line ""
Write-Line "Done. Reboot Windows, then reinstall vendor driver if needed and reconnect the controller."
