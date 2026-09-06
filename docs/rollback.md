# Rollback Procedure -- Huldra Hermes V1

## When to rollback

- The Huldra instance produces incorrect results
- The Huldra gateway fails to start or crashes repeatedly
- LATCH coupling leaks into Huldra surfaces
- Chris directs a rollback

## Prerequisites

- The original live Hermes process at `$env:LOCALAPPDATA\hermes` is still intact
- No irreversible changes have been made (no public push, no profile migration)

## Rollback steps

### 1. Stop the Huldra gateway (if running)

```powershell
# Find and kill any Huldra-pointed gateway process
Get-Process -Name python | Where-Object { $_.CommandLine -match "hermes" } | Stop-Process -Force
```

Or use the task manager to find and stop the process.

### 2. Resume the original live Hermes

```powershell
Set-Location <LIVE_HERMES_INSTALL>
.\venv\Scripts\hermes.exe gateway run
```

### 3. Restore HERMES_HOME

Ensure `HERMES_HOME` points back to the original location:

```powershell
$env:HERMES_HOME = "<LIVE_HERMES_HOME>"
```

Or remove the Huldra override from your environment/profile.

### 4. Verify live is restored

```powershell
# Check gateway is running
hermes gateway status

# Check config cwd is LATCH
hermes config get terminal.cwd
# Should show: <LEGACY_WORKSPACE>
```

### 5. Leave Huldra artifacts as-is

Do NOT delete `$env:HULDRA_HOME\ops\hermes`, `$env:HULDRA_HOME\boards\huldra`, or `$env:HULDRA_HOME\huldra-hermes-prep`. They are inert prep artifacts that may be useful for debugging.

## What does NOT need rollback

- `$env:HULDRA_HOME\docs\OBJECTIVE.md` -- never touched by Huldra work
- Live `HERMES_HOME` config -- never modified
- Live gateway process -- never restarted
- Live `state.db` / sessions -- never copied
- Live `.env` / credentials -- never read or written

## Post-rollback

- The Huldra V1 code tree remains available for future attempts
- The prep fork at `$env:HULDRA_HOME\huldra-hermes-prep` is still on branch `huldra-hermes-prep`
- The routing guards in `huldra_routing.py` can be re-evaluated
- If a public repository exists, remove the corresponding tag or branch and coordinate with collaborators on the rollback
