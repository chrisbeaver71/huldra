#Requires -Version 5.1
<#
.SYNOPSIS
  Zero-GPU Huldra status/doctor -- paths, config, routing guards (no model load).
  Set $env:HULDRA_HOME or pass explicit paths.
#>
param(
  [string]$HuldraHome,
  [string]$OpsRoot,
  [string]$PrepHome,
  [string]$Python = ''
)

$ErrorActionPreference = 'Continue'
$fail = 0
function Check([bool]$ok, [string]$msg) {
  if ($ok) { Write-Host "PASS  $msg" -ForegroundColor Green }
  else { Write-Host "FAIL  $msg" -ForegroundColor Red; $script:fail++ }
}

# Resolve paths
if (-not $HuldraHome) { $HuldraHome = $env:HULDRA_HOME }
if (-not $HuldraHome) { Write-Host 'ERROR: HULDRA_HOME not set' -ForegroundColor Red; exit 1 }
if (-not $OpsRoot)  { $OpsRoot  = Join-Path $HuldraHome 'ops\hermes' }
if (-not $PrepHome) { $PrepHome = Join-Path $HuldraHome 'huldra-hermes-prep-home' }

Write-Host '=== huldra doctor (zero-GPU) ===' -ForegroundColor White

Check (Test-Path "$OpsRoot\source") "ops source exists"
Check (Test-Path "$OpsRoot\config\config.example.yaml") "config.example.yaml"
Check (Test-Path "$OpsRoot\config\huldra.overlay.yaml") "huldra.overlay.yaml"
Check (Test-Path "$OpsRoot\config\.env.huldra.example") ".env.huldra.example"
Check (Test-Path "$OpsRoot\scripts\bootstrap-huldra.ps1") "bootstrap-huldra.ps1"
Check (Test-Path "$OpsRoot\scripts\launch-huldra.ps1") "launch-huldra.ps1"
Check (Test-Path "$OpsRoot\scripts\smoke-huldra.ps1") "smoke-huldra.ps1"
Check (Test-Path "$OpsRoot\README.md") "ops README"
Check (Test-Path "$OpsRoot\LICENSE") "ops LICENSE"
Check (Test-Path "$OpsRoot\docs\architecture.md") "architecture.md"
Check (Test-Path "$OpsRoot\docs\LATCH_BAGGAGE_QUARANTINE.md") "LATCH quarantine doc"
Check (Test-Path (Join-Path $HuldraHome 'boards\huldra')) "boards dir"
Check (Test-Path (Join-Path $HuldraHome '.hermes-live')) "status dir"
Check (Test-Path $PrepHome) "prep-home $PrepHome"

$liveHome = Join-Path $env:LOCALAPPDATA 'hermes'
Check (([IO.Path]::GetFullPath($PrepHome)) -ine ([IO.Path]::GetFullPath($liveHome))) "prep-home is not live HERMES_HOME"

# Config parse + no LATCH default cwd
$cfg = Join-Path $PrepHome 'config.yaml'
if (Test-Path $cfg) {
  Check $true "prep-home config.yaml present"
  $raw = Get-Content $cfg -Raw
  Check ($raw -notmatch '(?m)^\s*cwd:\s.*[Pp]roject [Ll]atch') "config cwd not Project LATCH"
} else {
  Check $false "prep-home config.yaml missing -- run bootstrap-huldra.ps1"
}

# Python routing import
if (-not $Python) {
  $Python = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
}
if ($Python -and (Test-Path $Python)) {
  $env:PYTHONPATH = "$OpsRoot\source"
  $huldraPath = $HuldraHome.Replace('\', '\\')
  $latchPath = 'C:\\Users\\generic\\project Latch'.Replace('\', '\\')
  $code = @"
import huldra_routing as hr
assert hr.is_huldra_path(r'$huldraPath')
assert not hr.is_huldra_path(r'$latchPath')
assert hr.is_huldra_channel('C0BKR5LEYV8')
assert not hr.is_huldra_channel('#latch')
print('routing_ok')
"@
  $out = & $Python -c $code 2>&1
  Check ($LASTEXITCODE -eq 0 -and ("$out" -match 'routing_ok')) "import routing + LATCH reject / Huldra accept ($out)"
} else {
  Check $false "Python not found for routing check"
}

Write-Host ''
if ($fail -eq 0) {
  Write-Host 'DOCTOR_OK' -ForegroundColor Green
  exit 0
} else {
  Write-Host "DOCTOR_FAIL count=$fail" -ForegroundColor Red
  exit 1
}
