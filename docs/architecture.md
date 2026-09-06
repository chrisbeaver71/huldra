# Architecture — Huldra Hermes V1

## Overview

Huldra Hermes V1 is a classified fork of the upstream Hermes Agent (Nous Research, v0.21.0) adapted for the Project Huldra operating environment. The fork preserves generic core machinery while removing LATCH-specific coupling and live-state material.

## Core components

```
                    ┌─────────────────────────┐
                    │   CLI (hermes_cli/)     │
                    │   gateway run / cron    │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Gateway (gateway/)    │
                    │   session, dispatch,    │
                    │   kanban watchers,      │
                    │   delivery/lifecycle     │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Agent (agent/)        │
                    │   tool loop, context,   │
                    │   compression, tools    │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
    ┌─────────▼──────┐ ┌───────▼────────┐ ┌──────▼──────┐
    │  Tools (tools/)│ │  Providers     │ │  Plugins    │
    │  kanban, exec, │ │  (providers/)  │ │  (plugins/) │
    │  browser, etc  │ │  openai, etc   │ │  memory, etc│
    └────────────────┘ └────────────────┘ └─────────────┘
```

## Data flow

1. **Inbound**: Slack/CLI message → Gateway session → Stream dispatch
2. **Processing**: Agent loop runs tool calls, manages context compression
3. **Tools**: Terminal, browser, kanban, code execution, file I/O
4. **Output**: Response streamed back through gateway to user/channel
5. **Receipts**: Delivery ledger, lifecycle ledger, status mirror

## Key paths

| Component | Location (in source/) |
|-----------|----------------------|
| Agent runtime | `agent/`, `run_agent.py`, `cli.py` |
| Gateway | `gateway/run.py`, `gateway/session*.py`, `gateway/stream_dispatch.py` |
| Kanban | `tools/kanban_tools.py`, `gateway/kanban_watchers.py` |
| Delivery/ledgers | `gateway/delivery_ledger.py`, `gateway/lifecycle_ledger.py` |
| Recovery | `gateway/session_db_recovery.py`, restart/drain helpers |
| Status | `gateway/status.py`, `gateway/disk_status.py` |
| Profile routing | `gateway/profile_routing.py` |
| Huldra guards | `huldra_prep/huldra_routing.py` |

## Huldra adaptations

The Huldra fork adds:

- **Path/channel guards**: `huldra_routing.py` rejects LATCH paths and `#latch` channel
- **Secret-free config**: `config/config.example.yaml` with Huldra defaults
- **Authority model**: Ansel → Hermes → Chris (not Shan/personal assistant)
- **State outside code tree**: boards, status mirror, evidence all external

## What was removed

- LATCH workspace `<LEGACY_WORKSPACE>` as default cwd
- `#latch` / `C0BKT3BEP4H` as coordination channel
- `profiles/latch` and shun* fleet profiles
- Mighty/B1 institutional gates
- Project LATCH HERMES.md gates
- AGY-CLI-LATCH smoke packages
- Real `.env`, credentials, session DBs, memory DBs

## Testing

- **Routing guards**: `tests/test_huldra_routing_guards.py` (7 tests)
- **V1 smoke**: `tests/test_v1_smoke.py` (layout/import/guard validation)
- **Upstream tests**: Full upstream test suite preserved for no-regression

## Limitations

- No live gateway integration yet (cutover is a separate card)
- Skills/cron bodies under live HERMES_HOME may still encode LATCH paths (UNKNOWN)
- Empty live `allowed_channels` semantics need verification before cutover
- Local tree is behind upstream; future merges will be large
