# HULDRA_FORK_AUDIT — Dependency Classification

Source: local live checkout `<LIVE_HERMES_INSTALL>`
@ `3a980a431b28633a5b79c462f654dc100dc1c598` (hermes-agent 0.21.0), forked to
worktree `<HULDRA_HOME>\huldra-hermes-prep` on branch `huldra-hermes-prep`.

Upstream NousResearch tree is generic; most LATCH coupling is in **live
HERMES_HOME overlays/config**, not in upstream package code (many code hits for
the word "latch" are unrelated state-machine latches).

## KEEP — Core agent / gateway / kanban / dispatch / receipts / recovery

| Area | Location (worktree) | Notes |
|---|---|---|
| Agent runtime | `agent/`, `run_agent.py`, `cli.py` | Core loop, tools, compression |
| Gateway | `gateway/run.py`, `gateway/session*.py`, `gateway/stream_dispatch.py` | Live operator surface |
| Kanban | `tools/kanban_tools.py`, `gateway/kanban_watchers.py`, config `kanban.*` | Dispatch interval, failure_limit |
| Dispatch in gateway | config `kanban.dispatch_in_gateway` | KEEP concept |
| Delivery / ledgers | `gateway/delivery_ledger.py`, `gateway/lifecycle_ledger.py` | Receipt-like trails |
| Recovery | `gateway/session_db_recovery.py`, restart/drain helpers | Reclaim / recovery |
| Status | `gateway/status.py`, `gateway/disk_status.py` | Status reporting |
| Profile routing (engine) | `gateway/profile_routing.py` | Engine KEEP; LATCH profile *data* is REMOVE |
| Authz / pairing | `gateway/authz_mixin.py`, `gateway/pairing.py` | Bounded integration |
| Toolsets | `toolsets.py`, platform_toolsets in config | KEEP slack/terminal/kanban toolsets |

## HULDRA-ADAPT — Live cwd / workspace / Slack / smart_policy / profiles

| Item | Live evidence | Adaptation |
|---|---|---|
| `terminal.cwd` | `<LEGACY_WORKSPACE>` in live `config.yaml` | → `<HULDRA_HOME>` in prep-home + example |
| Slack coordination | `#huldra` `C0BKR5LEYV8` exists; `#latch` `C0BKT3BEP4H` also present | Prefer `#huldra` only; guard in `huldra_routing.py` |
| `approvals.smart_policy` | Begins "Project LATCH / Mighty…" | Rewrite for Project HULDRA + Ansel→Hermes |
| Profiles | live `profiles\latch`, `shun*` etc. | Do not activate under prep-home; document quarantine |
| Status mirror | `<HULDRA_HOME>\.hermes-live` already used | Codify as Huldra convention |
| Authority | Live SOUL is "Shan" personal assistant | Huldra stub uses Ansel→Hermes→Chris |

## REMOVE-LATCH / quarantine — Do not carry forward

| Item | Why |
|---|---|
| Project LATCH path hardcoding | Wrong product root for Huldra |
| `#latch` defaults | Wrong coordination surface |
| Project LATCH `HERMES.md` gates | LATCH-specific operator contract |
| Mighty / B1 gates & mighty-* cache bodies | LATCH scientific gate stack |
| institutional_memory Latch pins | LATCH memory pins |
| `profiles/latch` as Huldra active profile | Couples prep to LATCH home |
| AGY-CLI-LATCH smoke packages | Historical LATCH operator evidence |

See `LATCH_BAGGAGE_QUARANTINE.md`.

## UNKNOWN

| Item | Question |
|---|---|
| Whether any skills under live HERMES_HOME encode LATCH paths beyond config | Needs deeper skill-body scan before cutover |
| Exact Project LATCH `HERMES.md` contents on disk at cutover time | Path may be Drive-synced; confirm before deleting references |
| Interaction of prep-home with editable install of live venv | Tests use live venv Python via PYTHONPATH only — permanent install into live env not done |
| Full dual-channel Slack allowlists when empty in config | Live `allowed_channels: ''` — runtime may use pairing/directory; verify before cutover |
| Mnemosyne / memories LATCH residue | Present in backups; not migrated |

## Classification summary

- **KEEP**: upstream agent/gateway/kanban/recovery/status machinery
- **HULDRA-ADAPT**: cwd, channels, smart_policy, docs/status conventions, authority model
- **REMOVE-LATCH**: LATCH paths, `#latch`, Mighty/B1/HERMES.md gates, latch profile activation
- **UNKNOWN**: skill-body residue, empty Slack allowlist semantics, memory residue
