[CmdletBinding()]
param(
    [ValidateSet('activate', 'rollback', 'status')]
    [string]$Action = 'status',
    [string]$HuldraHome = $env:HULDRA_HOME,
    [string]$PrepHome = '',
    [string]$PointerPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($HuldraHome)) {
    throw 'HuldraHome is required; pass -HuldraHome or set HULDRA_HOME.'
}
$HuldraHome = [IO.Path]::GetFullPath($HuldraHome)
if ([string]::IsNullOrWhiteSpace($PointerPath)) {
    $PointerPath = Join-Path $HuldraHome 'boards\huldra\active-pointer.json'
}
$PointerPath = [IO.Path]::GetFullPath($PointerPath)
$pointerDir = Split-Path -Parent $PointerPath
New-Item -ItemType Directory -Force -Path $pointerDir | Out-Null

function Get-Pointer {
    if (-not (Test-Path -LiteralPath $PointerPath -PathType Leaf)) {
        return $null
    }
    return Get-Content -LiteralPath $PointerPath -Raw | ConvertFrom-Json
}

function Write-Pointer([hashtable]$Value) {
    $tmp = "$PointerPath.$([guid]::NewGuid().ToString('N')).tmp"
    $json = $Value | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($tmp, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tmp -Destination $PointerPath -Force
}

function Resolve-Existing([string]$Value, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Value) -or -not (Test-Path -LiteralPath $Value -PathType Container)) {
        throw "$Label must be an existing directory."
    }
    return ([IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Value).Path))
}

$now = [DateTime]::UtcNow.ToString('o')
$old = Get-Pointer

switch ($Action) {
    'status' {
        if ($null -eq $old) {
            [ordered]@{ schema = 'HULDRA_ACTIVE_POINTER_V1'; status = 'uninitialized'; pointer_path = $PointerPath } | ConvertTo-Json -Depth 6
        } else {
            $old | ConvertTo-Json -Depth 8
        }
        exit 0
    }
    'activate' {
        $target = Resolve-Existing $PrepHome 'PrepHome'
        $previous = if ($null -ne $old -and $old.previous_root) {
            [string]$old.previous_root
        } elseif ($env:HERMES_HOME) {
            [IO.Path]::GetFullPath($env:HERMES_HOME)
        } else {
            [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hermes'))
        }
        $value = [ordered]@{
            schema = 'HULDRA_ACTIVE_POINTER_V1'
            status = 'active'
            scope = 'isolated-prep-only'
            active_root = $target
            previous_root = $previous
            activated_at_utc = $now
            rollback_supported = $true
            live_process_mutated = $false
            credentials_read = $false
        }
        Write-Pointer $value
        $value | ConvertTo-Json -Depth 8
        exit 0
    }
    'rollback' {
        if ($null -eq $old -or -not $old.previous_root) {
            throw 'No active pointer with a recorded previous_root exists.'
        }
        $value = [ordered]@{
            schema = 'HULDRA_ACTIVE_POINTER_V1'
            status = 'rolled_back'
            scope = 'isolated-prep-only'
            active_root = [string]$old.previous_root
            previous_root = [string]$old.active_root
            rolled_back_at_utc = $now
            rollback_supported = $true
            live_process_mutated = $false
            credentials_read = $false
        }
        Write-Pointer $value
        $value | ConvertTo-Json -Depth 8
        exit 0
    }
}
