#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap Huldra Hermes V1 layout for local smoke (never live HERMES_HOME).
.DESCRIPTION
  Verifies/creates Huldla ops/hermes layout dirs, prep-home, boards/status paths.
  Does NOT copy secrets, state.db, or touch $env:LOCALAPPDATA\hermes.
  Set $env:HULDRA_HOME or pass explicit paths.
#>
param(
  [string]$HuldraHome,
  [string]$OpsRoot,
  [string]$PrepHome,
  [string]$Boards,
  [string]$Status,
  [switch]$SkipDirs
)

$ErrorActionPreference = 'Stop'
function Fail([string]$m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }
function Ok([string]$m) { Write-Host "OK: $m" -ForegroundColor Green }
function Info([string]$m) { Write-Host "INFO: $m" -ForegroundColor Cyan }

# Resolve HULDRA_HOME from param or env
if (-not $HuldraHome) { $HuldraHome = $env:HULDRA_HOME }
if (-not $HuldraHome) { Fail "HULDRA_HOME not set. Set `$env:HULDRA_HOME or pass -HuldraHome <path>." }

if (-not $OpsRoot)  { $OpsRoot  = Join-Path $HuldraHome 'ops\hermes' }
if (-not $PrepHome) { $PrepHome = Join-Path $HuldraHome 'huldra-hermes-prep-home' }
if (-not $Boards)   { $Boards   = Join-Path $HuldraHome 'boards\huldra' }
if (-not $Status)   { $Status   = Join-Path $HuldraHome '.hermes-live' }

Write-Host '=== Huldra Hermes bootstrap ===' -ForegroundColor White
Write-Host "HuldlaHome: $HuldraHome"
Write-Host "OpsRoot:  $OpsRoot"
Write-Host "PrepHome: $PrepHome (smoke only -- never live HERMES_HOME)"

# Refuse live HERMES_HOME
$liveHome = Join-Path $env:LOCALAPPDATA 'hermes'
if ($PrepHome -and (Resolve-Path -LiteralPath $PrepHome -ErrorAction SilentlyContinue)) {
  $resolvedPrep = (Resolve-Path -LiteralPath $PrepHome).Path
  if ($resolvedPrep -ieq $liveHome) {
    Fail "PrepHome must not be live HERMES_HOME ($liveHome). Use $PrepHome."
  }
}

foreach ($req in @("$OpsRoot\source", "$OpsRoot\config", "$OpsRoot\scripts", "$OpsRoot\tests", "$OpsRoot\docs")) {
  if (-not (Test-Path $req)) { Fail "Missing required path: $req -- populate ops tree first." }
  Ok "found $req"
}

if (-not (Test-Path "$OpsRoot\config\config.example.yaml")) {
  Fail "Missing config\config.example.yaml (secret-free overlay)."
}
Ok 'secret-free config.example.yaml present'

if (-not $SkipDirs) {
  foreach ($d in @($PrepHome, $Boards, $Status, (Join-Path $HuldraHome 'Results'), (Join-Path $HuldraHome 'evidence'))) {
    if (-not (Test-Path $d)) {
      New-Item -ItemType Directory -Path $d -Force | Out-Null
      Info "created $d"
    } else {
      Ok "dir exists $d"
    }
  }
}

# Seed prep-home config from overlay if missing
$prepCfg = Join-Path $PrepHome 'config.yaml'
$overlay = Join-Path $OpsRoot 'config\huldra.overlay.yaml'
if (-not (Test-Path $prepCfg)) {
  if (Test-Path $overlay) {
    Copy-Item $overlay $prepCfg
    Info "seeded $prepCfg from huldra.overlay.yaml (secret-free)"
  } else {
    Fail "No prep-home config and no overlay to seed."
  }
} else {
  Ok "prep-home config present: $prepCfg"
}

# Guard: refuse if overlay/config defaults to LATCH cwd (non-comment)
$cfgText = Get-Content $prepCfg -Raw -ErrorAction SilentlyContinue
if ($cfgText -match '(?m)^\s*cwd:\s.*project Latch') {
  Fail "prep-home config still defaults cwd to Project LATCH -- fix before smoke."
}
Ok 'prep-home cwd is not Project LATCH'

Write-Host ''
Write-Host 'Next:' -ForegroundColor Yellow
Write-Host "  .\scripts\huldra-doctor.ps1"
Write-Host "  .\scripts\smoke-huldra.ps1"
Write-Host "  .\scripts\launch-huldra.ps1   # smoke gateway only; never live"
Write-Host ''
Ok 'bootstrap complete'
