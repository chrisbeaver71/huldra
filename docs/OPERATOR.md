# Huldra Hermes V1 -- operator one-pager

## What runs where

| Tree | Role |
|------|------|
| `$env:HULDRA_HOME\ops\hermes` | Permanent product home (source, config, scripts, tests, docs) |
| `$env:HULDRA_HOME\huldra-hermes-prep` | Git staging / fork branch `huldra-hermes-prep` |
| `$env:HULDRA_HOME\huldra-hermes-prep-home` | Isolated HERMES_HOME for smoke only |
| `$env:LOCALAPPDATA\hermes` | **Live** Hermes -- do not mutate from product scripts |

## First run (Windows)

```powershell
# Set HULDRA_HOME to wherever you cloned/installed this repo
$env:HULDRA_HOME = (Get-Location).Path
Set-Location "$env:HULDRA_HOME\ops\hermes"
.\scripts\bootstrap-huldra.ps1
.\scripts\huldra-doctor.ps1
.\scripts\smoke-huldra.ps1
```

Launch smoke gateway (prep-home only -- never live):

```powershell
.\scripts\launch-huldra.ps1
```

## Product defaults

- cwd: `$env:HULDRA_HOME`
- Slack: `#huldra` / `C0BKR5LEYV8`
- Boards/state: `$env:HULDRA_HOME\boards\huldra`
- Status: `$env:HULDRA_HOME\.hermes-live`
- Secrets: fill from `config\.env.huldra.example` into prep-home `.env` (never commit)

## Hard no

- Do not default to Project LATCH / `#latch` / `profiles/latch`
- Do not copy live `.env` / `state.db` into `ops\hermes\config`
- Do not edit `$env:HULDRA_HOME\docs\OBJECTIVE.md` from agent automation
- Do not restart live `hermes.exe gateway` from these scripts

## Authority

Ansel sets intent -> Hermes executes within Huldra -> Chris approves irreversible / spend / deploy.
