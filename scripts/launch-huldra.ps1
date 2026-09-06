#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Huldra Hermes against prep-home for smoke (never live HERMES_HOME).
.DESCRIPTION
  Sets HERMES_HOME to $env:HULDRA_HOME\huldra-hermes-prep-home and runs gateway from ops source.
  Refuses if HERMES_HOME would be the live LocalAppData hermes tree.
  Set $env:HULDRA_HOME or pass explicit paths.
#>
param(
  [string]$HuldraHome,
  [string]$OpsRoot,
  [string]$PrepHome,
  [string]$Python = '',
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ArgsRest = @('gateway')
)

$ErrorActionPreference = 'Stop'
function Fail([string]$m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

# Resolve paths
if (-not $HuldraHome) { $HuldraHome = $env:HULDRA_HOME }
if (-not $HuldraHome) { Fail "HULDRA_HOME not set. Set `$env:HULDRA_HOME or pass -HuldraHome <path>." }
if (-not $OpsRoot)  { $OpsRoot  = Join-Path $HuldraHome 'ops\hermes' }
if (-not $PrepHome) { $PrepHome = Join-Path $HuldraHome 'huldra-hermes-prep-home' }

$liveHome = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hermes'))
$prepFull = [IO.Path]::GetFullPath($PrepHome)
if ($prepFull -ieq $liveHome) {
  Fail "Refusing to launch with live HERMES_HOME ($liveHome). Use prep-home."
}

if (-not (Test-Path "$OpsRoot\source")) { Fail "ops source missing: $OpsRoot\source" }
if (-not (Test-Path $PrepHome)) {
  Fail "PrepHome missing: $PrepHome -- run .\scripts\bootstrap-huldra.ps1 first."
}

if (-not $Python) {
  $candidates = @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
  ) | Where-Object { $_ -and (Test-Path $_) }
  if (-not $candidates) { Fail 'No Python found. Pass -Python path.' }
  $Python = $candidates[0]
}

$env:HERMES_HOME = $prepFull
$env:HULDRA_ROOT = $HuldraHome
# Do not inherit live profiles/latch
Remove-Item Env:HERMES_PROFILE -ErrorAction SilentlyContinue

Write-Host "HERMES_HOME=$env:HERMES_HOME (prep only)" -ForegroundColor Cyan
Write-Host "Python=$Python"
Write-Host "cwd source=$OpsRoot\source"
Write-Host "args: $($ArgsRest -join ' ')"
Write-Host 'NOTE: This does not start/restart live hermes.exe gateway.' -ForegroundColor Yellow

Push-Location "$OpsRoot\source"
try {
  & $Python -m hermes_cli.main @ArgsRest
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
