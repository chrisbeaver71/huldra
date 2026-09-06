# HULDRA_HERMES_PREP_REPORT

Generated: 2026-09-05 23:14:23 PT

## 1) Source repo / path / commit identified + evidence

| Field | Value |
|---|---|
| Code path | `<LIVE_HERMES_INSTALL>` |
| Remote | `https://github.com/NousResearch/hermes-agent.git` |
| Commit | `3a980a431b28633a5b79c462f654dc100dc1c598` on `main` |
| Package | hermes-agent **0.21.0** (`pyproject.toml`) |
| Drift | `main...origin/main [behind 4863]` — local checkout is source of truth; remote NOT cloned |
| Live process | `hermes.exe gateway run` from `...\hermes-agent\venv\Scripts\hermes.exe` (PID 11484 + python wrappers) |
| HERMES_HOME | `<LIVE_HERMES_HOME>` |
| Live config cwd | `terminal.cwd: <LEGACY_WORKSPACE>` in live `config.yaml` |
| Huldra status mirror | `<HULDRA_HOME>\.hermes-live` (HermesLiveStatus.txt present) |
| Channels | `#huldra`/`C0BKR5LEYV8`, `#latch`/`C0BKT3BEP4H` both in `channel_directory.json` |

**Evidence notes:** Git HEAD/remote/branch verified before fork. Editable install confirmed via `pyproject.toml` name/version. Gateway command line matched confirmed identity. Live config cwd matched LATCH workspace. No remote NousResearch clone performed.

## 2) Fork / branch / worktree location

| Item | Path |
|---|---|
| Worktree | `<HULDRA_HOME>\huldra-hermes-prep` |
| Branch | `huldra-hermes-prep` (from HEAD `3a980a431b`) |
| Prep home (isolated) | `<HULDRA_HOME>\huldra-hermes-prep-home\` |
| Live worktree | unchanged on `main` @ same commit |

Git worktree list:
- `<LIVE_HERMES_INSTALL>` -> `main` @ `3a980a431b`
- `<HULDRA_HOME>/huldra-hermes-prep` -> `huldra-hermes-prep` @ tip below

## 3) Concise architecture map (KEEP core)

```
Slack/CLI -> gateway/run.py (session, stream_dispatch, kanban_watchers)
         -> agent/ + run_agent.py (tool loop)
         -> tools/kanban_tools.py (task cards / dispatch)
         -> delivery_ledger / lifecycle_ledger / status (receipts & reporting)
         -> session_db_recovery / restart_* (recovery/reclaim)
Config overlays (HERMES_HOME): cwd, smart_policy, profiles, Slack allowlists
```

Huldra prep adds **guards + docs + sanitized prep-home config** without wiring into the live gateway.

## 4) LATCH baggage removed / quarantined

Documented in `LATCH_BAGGAGE_QUARANTINE.md` and classified in `HULDRA_FORK_AUDIT.md`.

Removed from prep defaults:
- `terminal.cwd` no longer LATCH path (prep-home -> `<HULDRA_HOME>`)
- smart_policy rewritten away from "Project LATCH / Mighty"
- `#latch` / LATCH roots rejected by `huldra_routing` helpers

Quarantined (not carried into prep-home activation):
- `profiles/latch`, shun* fleet profiles
- Project LATCH HERMES.md / Mighty B1 / institutional_memory Latch pins
- Live state DBs, real `.env`, AGY-CLI-LATCH smoke packages

## 5) Huldra adaptations made (worktree + prep-home only)

| Artifact | Purpose |
|---|---|
| `huldra_prep/huldra_routing.py` (+ top-level `huldra_routing.py` shim) | Path/channel guards |
| `huldra_prep/config.example.yaml` | Secret-free Huldra defaults |
| `<HULDRA_HOME>\huldra-hermes-prep-home\config.yaml` | Sanitized live-derived config (secrets -> placeholders; cwd Huldra) |
| `HERMES_HULDRA.md` | Operating stub |
| `LATCH_BAGGAGE_QUARANTINE.md` | Explicit non-carry list |
| `HULDRA_FORK_AUDIT.md` | KEEP / HULDRA-ADAPT / REMOVE-LATCH / UNKNOWN |
| `tests/test_huldra_routing_guards.py` | Guard tests |

Authority note: Ansel -> Hermes execution; Chris for irreversible actions. Results/docs/live-status conventions point at `<HULDRA_HOME>/Results`, `<HULDRA_HOME>/docs`, `<HULDRA_HOME>/.hermes-live`.

## 6) Tests / checks run and results

| Check | Result |
|---|---|
| `pytest tests/test_huldra_routing_guards.py -q` via live venv Python + `PYTHONPATH=worktree` | **7 passed** |
| `python -c "import huldra_routing"` | **ok** |
| PyYAML parse prep-home `config.yaml` + example | **ok** (`cwd=<HULDRA_HOME>`) |
| Live gateway start | **NOT run** (by design) |
| Permanent install into live venv | **NOT done** |

## 7) Diff / commit refs (local only; not pushed)

On branch huldra-hermes-prep (tip 84a810b0c315ef9d9c81e0b70b79b7617838b79d):
1. 95937aa4227b673398b619b5d9dd90f9cfec7ed1 -- prep(huldra): isolated Hermes->Huldra routing guards, audit, and stub docs
2. 22b805fa9e5a9c0783adbb3958bbbc75871ad0ae -- docs(huldra): record prep commit hash in report
3. 84a810b0c315ef9d9c81e0b70b79b7617838b79d -- docs(huldra): finalize prep report with live verification

Not pushed. Live main has none of these files.

## 8) Unresolved blockers / risks

1. **CUTOVER NOT READY** — no live gateway swap, no Slack allowlist cutover, no profile migration.
2. Skill/cron bodies under live HERMES_HOME may still encode LATCH paths (UNKNOWN in audit).
3. Empty live `allowed_channels` semantics vs pairing/directory need verification before cutover.
4. Local tree is **4863 commits behind origin**; future upstream merges will be large — treat carefully; do not fast-forward live blindly.
5. Prep-home has **no real `.env`** — cannot run authenticated gateway smoke without separate secret injection (out of scope).
6. Pre-existing weird untracked filename in live worktree (unrelated; left untouched).

## 9) CUTOVER READINESS

**CUTOVER READINESS: NOT READY**

Reasons:
- Live operator still authoritative and intentionally untouched
- Guards/docs/tests exist but are not integrated into gateway startup hooks
- No dual-run / shadow validation against `#huldra`
- Secrets/env and Slack routing cutover not performed
- OBJECTIVE.md and live config/process left unchanged (correct for prep; insufficient for cutover)

**REVIEW READY** for engineering review of the prep fork artifacts only.

## 10) Live untouched verification (post-work)

Confirmed after prep commits:
- Live branch still `main` @ `3a980a431b28633a5b79c462f654dc100dc1c598`
- Live `git status` shows only pre-existing unrelated untracked odd filename — **no prep files**
- `hermes.exe gateway run` still from original venv path (PID 11484)
- Live `config.yaml` `cwd` still `<LEGACY_WORKSPACE>` (unchanged)
- `<HULDRA_HOME>\docs\OBJECTIVE.md` present; LastWriteTime `2026-09-02 22:26:33` local (not modified by this work)
