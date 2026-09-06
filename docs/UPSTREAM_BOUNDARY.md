# Upstream Boundary — Huldra over Hermes

This document records the exact upstream base, the Huldra-owned surface,
conflict hotspots, and rollback procedure. It is the authoritative
reference for what belongs to upstream Hermes and what belongs to Huldra.

## Upstream Base

- **Upstream**: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
  (Nous Research, MIT License)
- **Fork point**: The initial Huldra V1 release candidate was built on
  top of the upstream Hermes Agent code (v0.21.0 per architecture.md).
- **Upstream tracked ref**: `upstream/main` at `693641aa8b4359c602283bdbbc14041e03bc47bc`
  ("fix(chat-completions): strip name from tool-result messages for
  strict providers", 2026-08-17)
- **Initial fork commit**: `b32d0ca` ("Huldra Hermes V1 release
  candidate") — 2026-09-06 15:24:52 -0700
- **Current HEAD**: `0b0212f` ("docs: remove remaining local install
  paths") — 2026-09-06 15:59:47 -0700
- **Commits since fork**: 5 (documentation + publication polish only;
  no upstream code changes)
- **Remotes**:
  - `origin` → `https://github.com/chrisbeaver71/huldra.git`
    (the Huldra publication repo)
  - `upstream` → `https://github.com/NousResearch/hermes-agent.git`
    (read-only upstream tracking)

To establish an upstream tracking remote for future syncs:

```bash
cd E:/Huldra/ops/hermes
git remote add upstream https://github.com/NousResearch/hermes-agent.git
git fetch upstream
git log --oneline upstream/master -5  # confirm the base
```

## Huldra-Owned Surface

These files are Huldra additions or Huldra-specific adaptations. They
must not be overwritten by an upstream merge and must be reconciled
whenever upstream files they depend on change.

### Source (adapter/facade layer)

| File | Purpose |
|------|---------|
| `source/huldra_facade.py` | Thin adapter/facade orchestrating all Huldra product operations |
| `source/huldra_profiles.py` | Versioned profile catalog and schema |
| `source/huldra_hardware.py` | Deterministic hardware detection |
| `source/huldra_recommender.py` | Profile recommendation engine |
| `source/huldra_chat.py` | Chat session on top of LocalModelBackend |
| `source/huldra_tools.py` | Tool invocation bridge and V1 tool set |
| `source/huldra_file_context.py` | Bounded file/desktop context boundary |
| `source/huldra_state.py` | Lightweight durable state outside code tree |
| `source/huldra_status.py` | Recovery/status visibility |
| `source/huldra_routing.py` | Re-export from huldra_prep |
| `source/huldra_prep/__init__.py` | Huldra routing package |
| `source/huldra_prep/huldra_routing.py` | Path and Slack channel guards |
| `source/huldra_prep/config.example.yaml` | Huldra-specific config template |

### Config

| File | Purpose |
|------|---------|
| `config/huldra.overlay.yaml` | Secret-free product overlay |
| `config/.env.huldra.example` | Secret-free env template |
| `config/config.example.yaml` | Config example (Huldra defaults) |
| `config/README.md` | Config directory notes |

### Scripts

| File | Purpose |
|------|---------|
| `scripts/bootstrap-huldra.ps1` | Layout verification + prep-home seed |
| `scripts/launch-huldra.ps1` | Prep-home smoke gateway launch |
| `scripts/smoke-huldra.ps1` | One-command smoke suite |
| `scripts/huldra-doctor.ps1` | Zero-GPU path/config/routing checks |
| `scripts/huldra-pointer.ps1` | Reversible pointer activation |
| `scripts/save_default_catalog.py` | Catalog persistence helper |

### Tests

| File | Purpose |
|------|---------|
| `tests/test_v1_smoke.py` | Layout/import/guard smoke |
| `tests/test_v1_product.py` | Backend/chat/tool/state/status tests |
| `tests/test_v1_profiles.py` | Profile catalog/hardware/recommender tests |
| `tests/test_v1_boundary.py` | Adapter boundary + profile integration |
| `tests/test_huldra_routing_guards.py` | Routing guard tests |

### Docs

| File | Purpose |
|------|---------|
| `docs/UPSTREAM_BOUNDARY.md` | This file |
| `docs/UPSTREAM_SYNC.md` | Upstream sync/rebase procedure |
| `docs/OPERATOR.md` | Operator one-pager |
| `docs/architecture.md` | Architecture overview |
| `docs/rollback.md` | Rollback procedure |
| `docs/LATCH_BAGGAGE_QUARANTINE.md` | LATCH quarantine docs |
| `docs/HULDRA_FORK_AUDIT.md` | Fork audit |

### Other

| File | Purpose |
|------|---------|
| `ATTRIBUTION.md` | Upstream attribution |
| `LICENSE` | MIT license |
| `README.md` | Project README |
| `V1_SHIP_CHECKLIST.md` | Ship checklist |

## Upstream Files (Not Modified)

The following upstream Hermes files are preserved unmodified. An upstream
merge should bring these forward cleanly:

- `source/agent/` (full directory)
- `source/gateway/` (full directory)
- `source/tools/` (full directory)
- `source/providers/` (full directory)
- `source/plugins/` (full directory)
- `source/skills/` (full directory)
- `source/cron/` (full directory)
- `source/hermes_cli/` (full directory)
- `source/acp_adapter/` (full directory)
- `source/hermes_constants.py`
- `source/hermes_logging.py`
- `source/hermes_state.py`
- `source/hermes_state_common.py`
- `source/hermes_state_portability.py`
- `source/hermes_state_registry.py`
- `source/hermes_state_schema.py`
- `source/hermes_state_search.py`
- `source/hermes_time.py`
- `source/hermes_bootstrap.py`
- `source/hermes_startup_watchdog.py`
- `source/backend.py`
- `source/batch_runner.py`
- `source/cli.py`
- `source/mcp_serve.py`
- `source/mini_swe_runner.py`
- `source/model_tools.py`
- `source/run_agent.py`
- `source/toolset_distributions.py`
- `source/toolsets.py`
- `source/trajectory_compressor.py`
- `source/utils.py`
- `source/registration_lifecycle.py`
- `source/pyproject.toml`
- `source/setup.py`
- `source/package.json`
- `source/.env.example`
- `source/.nvmrc`
- `source/.python-version`
- `source/LICENSE`

## Conflict Hotspots

These areas are most likely to produce merge conflicts when upstream
Hermes evolves:

1. **`source/cli.py`** — large (1MB), frequently updated upstream;
   Huldra does not modify it but it may conflict with path-dependent
   imports if upstream renames modules.
2. **`source/gateway/`** — the gateway is upstream's primary evolution
   surface. Huldra has no gateway modifications but depends on its
   API contracts.
3. **`source/backend.py`** — Huldra chat depends on BackendConfig,
   LocalModelBackend, and error types. Upstream renames will break
   `huldra_chat.py`.
4. **`tests/conftest.py`** — large (74KB), upstream evolution may
   change fixtures that Huldra tests depend on.
5. **`source/hermes_constants.py`** — Huldra config references
   constants that may shift.

## Rollback

To roll back to pure upstream Hermes (no Huldra adaptations):

1. Stop any Huldra-pointed gateway (`launch-huldra.ps1`).
2. Resume the original live Hermes from `$env:LOCALAPPDATA\hermes`.
3. Restore `HERMES_HOME` to `$env:LOCALAPPDATA\hermes`.
4. Leave `ops/hermes/` and `boards/huldra/` as inert prep artifacts.
5. The Huldra facade modules (`huldra_*.py`) are additive and do not
   modify any upstream file. Removing them restores upstream behavior
   with no residual side effects.

See `docs/rollback.md` for the full procedure.

## Design Principle

**Huldra over Hermes, not a deep fork.** The Huldra product layer is a
thin adapter/facade sitting on top of upstream Hermes machinery. Huldra
does not spread policy into Hermes core, does not rewrite working Hermes
machinery, and keeps all Huldra-owned state/config/assets under
`E:/Huldra/config`, `E:/Huldra/Models`, and `E:/Huldra/evidence`
rather than in the upstream code tree.
