#Requires -Version 5.1
<#
.SYNOPSIS
  One-command Huldra V1 smoke: doctor + routing pytest + layout checks.
  Uses live venv Python as interpreter only (PYTHONPATH to ops/staging source).
  Does NOT pip-install into live venv. Does NOT start live gateway.
  Set $env:HULDRA_HOME or pass explicit paths.
#>
param(
  [string]$HuldraHome,
  [string]$OpsRoot,
  [string]$Staging,
  [string]$Python = ''
)

$ErrorActionPreference = 'Continue'
$fail = 0

# Resolve paths
if (-not $HuldraHome) { $HuldraHome = $env:HULDRA_HOME }
if (-not $HuldraHome) { Write-Host 'ERROR: HULDRA_HOME not set' -ForegroundColor Red; exit 1 }
if (-not $OpsRoot)  { $OpsRoot  = Join-Path $HuldraHome 'ops\hermes' }
if (-not $Staging)  { $Staging  = Join-Path $HuldraHome 'huldra-hermes-prep' }

if (-not $Python) {
  $Python = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
}
if (-not $Python -or -not (Test-Path $Python)) {
  Write-Host 'ERROR: Python not found' -ForegroundColor Red
  exit 1
}

Write-Host "=== smoke-huldra ===" -ForegroundColor White
Write-Host "Python=$Python"

# 1) doctor
& "$OpsRoot\scripts\huldra-doctor.ps1" -HuldraHome $HuldraHome -OpsRoot $OpsRoot -Python $Python
if ($LASTEXITCODE -ne 0) { $fail++; Write-Host 'doctor failed' -ForegroundColor Red } else { Write-Host 'doctor passed' -ForegroundColor Green }

# 2) routing guards via pytest (staging tests; PYTHONPATH=staging)
$env:PYTHONPATH = $Staging
Push-Location $Staging
try {
  & $Python -m pytest tests/test_huldra_routing_guards.py -v --tb=short
  if ($LASTEXITCODE -ne 0) { $fail++; Write-Host 'routing pytest failed' -ForegroundColor Red } else { Write-Host 'routing pytest passed' -ForegroundColor Green }
} finally { Pop-Location }

# 3) ops v1 smoke (PYTHONPATH=ops source)
$env:PYTHONPATH = "$OpsRoot\source"
Push-Location $OpsRoot
try {
  & $Python -m pytest tests/test_v1_smoke.py -v --tb=short
  if ($LASTEXITCODE -ne 0) { $fail++; Write-Host 'v1 smoke pytest failed' -ForegroundColor Red } else { Write-Host 'v1 smoke pytest passed' -ForegroundColor Green }
} finally { Pop-Location }

# 4) YAML parse secret-free config (quarantine mentions OK; active cwd/channel defaults not OK)
$huldraHomeEsc = $HuldraHome.Replace('\', '\\')
$yamlCheck = @"
from pathlib import Path
import re
p = Path(r'$OpsRoot\config\config.example.yaml')
text = p.read_text(encoding='utf-8')
assert 'C0BKR5LEYV8' in text
assert 'boards_dir' in text or 'boards/huldra' in text
# Active defaults must not set LATCH cwd/channel/profile as assigned values
for line in text.splitlines():
    s = line.strip()
    if not s or s.startswith('#'):
        continue
    lower = s.lower()
    # quarantine / reject prose inside folded scalars is OK
    if any(k in lower for k in ('do not', 'quarantine', 'not carried', 'forbidden', 'reject', 'must not')):
        continue
    if re.match(r'^(cwd|channel|profile|home)\s*:', lower) and ('latch' in lower or 'project latch' in lower):
        raise SystemExit('LATCH active default: ' + s)
    if re.match(r'^\w+_channel(_id)?\s*:', lower) and ('latch' in lower or 'c0bkt3bep4h' in lower):
        raise SystemExit('LATCH channel default: ' + s)
print('yaml_ok')
"@
$out = & $Python -c $yamlCheck 2>&1
if ($LASTEXITCODE -eq 0 -and ("$out" -match 'yaml_ok')) {
  Write-Host 'PASS  secret-free YAML overlay' -ForegroundColor Green
} else {
  Write-Host "FAIL  YAML check: $out" -ForegroundColor Red
  $fail++
}

Write-Host ''
if ($fail -eq 0) {
  Write-Host 'SMOKE_OK' -ForegroundColor Green
  exit 0
} else {
  Write-Host "SMOKE_FAIL count=$fail" -ForegroundColor Red
  exit 1
}
