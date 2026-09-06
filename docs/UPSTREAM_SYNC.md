# Upstream Sync Procedure — Huldra over Hermes

This document describes the procedure for syncing Huldra with upstream
Hermes without breaking the adapter boundary.

## Prerequisites

1. The upstream remote is configured (already provisioned):
   ```bash
   cd E:/Huldra/ops/hermes
   # upstream → https://github.com/NousResearch/hermes-agent.git
   git fetch upstream
   # Current tracked: 693641aa (2026-08-17)
   ```

2. All Huldra modifications are committed on the current branch.

3. The adapter boundary test passes:
   ```bash
   cd E:/Huldra/ops/hermes
   python -m pytest tests/test_v1_boundary.py -v
   ```

## Sync Procedure

### Step 1: Fetch upstream

```bash
cd E:/Huldra/ops/hermes
git fetch upstream
```

### Step 2: Create a sync branch

```bash
git checkout -b sync/upstream-YYYYMMDD
```

### Step 3: Attempt merge

```bash
git merge upstream/main --no-edit
```

If this succeeds cleanly, skip to Step 7.

### Step 4: Resolve conflicts

Conflict hotspots (see `docs/UPSTREAM_BOUNDARY.md`):

| File | Resolution |
|------|-----------|
| `source/cli.py` | Accept upstream (Huldra does not modify) |
| `source/gateway/*` | Accept upstream (Huldra does not modify) |
| `source/backend.py` | Accept upstream, then verify `huldra_chat.py` imports still work |
| `source/hermes_constants.py` | Accept upstream, then check Huldra config references |
| `tests/conftest.py` | Accept upstream, then run Huldra test suite |

For each conflict:
1. Accept the upstream version.
2. Check if any Huldra module imports the changed symbol.
3. If an import breaks, update the Huldra module to match the new API.
4. Do NOT add Huldra policy to upstream files.

### Step 5: Run the adapter boundary test

```bash
cd E:/Huldra/ops/hermes
python -m pytest tests/test_v1_boundary.py -v
```

This test verifies:
- The facade can be imported
- The profile catalog loads
- All Huldra adapter modules import cleanly
- The adapter boundary is present (Huldra modules are additive, not invasive)

### Step 6: Run the full Huldra test suite

```bash
python -m pytest tests/test_v1_smoke.py tests/test_v1_product.py tests/test_v1_profiles.py tests/test_huldra_routing_guards.py tests/test_v1_boundary.py -v
```

All tests must pass. If a test fails due to an upstream API change,
fix the Huldra adapter module — never modify the upstream file to
accommodate Huldra.

### Step 7: Commit the merge

```bash
git add -A
git commit -m "sync: merge upstream YYYYMMDD into Huldra"
```

### Step 8: Update the boundary document

Edit `docs/UPSTREAM_BOUNDARY.md`:
- Update the "Current HEAD" field
- Update the "Commits since fork" count
- Note any new Huldra-owned files or changed conflict hotspots

## Rollback

If the merge breaks something:

```bash
git merge --abort  # if mid-merge
# or
git checkout main  # if committed but broken
git branch -D sync/upstream-YYYYMMDD
```

The Huldra facade modules are additive — removing them restores
upstream behavior with no residual side effects.

## Conflict Avoidance

To minimize future conflicts:

1. Keep Huldra adapter modules thin — they import from upstream but
   do not modify upstream files.
2. Avoid depending on upstream internal APIs; prefer stable public
   interfaces (BackendConfig, LocalModelBackend, etc.).
3. If upstream renames a module you depend on, update your import in
   the adapter layer, not in the upstream file.
4. Run the boundary test after every upstream sync.

## Smoke Test After Sync

After any upstream sync, run this quick verification:

```bash
cd E:/Huldra/ops/hermes
python -c "
import sys; sys.path.insert(0, 'source')
from huldra_facade import HuldraFacade
from huldra_profiles import create_v1_default_catalog
from huldra_hardware import HardwareProfile
from huldra_recommender import recommend_profiles
from huldra_chat import ChatSession
from huldra_tools import ToolRegistry
from huldra_file_context import PathGuard
from huldra_state import StateStore
from huldra_status import StatusTracker
print('All Huldra adapter modules import successfully')
catalog = create_v1_default_catalog()
print(f'Catalog loaded: {len(catalog.profiles)} profiles')
facade = HuldraFacade()
print(f'Facade initialized at {facade.huldra_home}')
print('UPSTREAM SYNC SMOKE: PASS')
"
```
