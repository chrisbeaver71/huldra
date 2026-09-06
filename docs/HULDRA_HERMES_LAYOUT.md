# HULDRA_HERMES_LAYOUT — Permanent filesystem plan (prep)

Status: **LAYOUT SPEC ADDED** to isolated fork work. Live Hermes untouched.
Generated: 2026-09-05 ~23:16 PT (from #huldra latch request).

## Constraints (binding)

- Fork stays isolated / non-destructive.
- Live Hermes remains authoritative until an explicit Chris-approved cutover.
- No auto-merge, deployment, cutover, or mutation of canonical live Hermes.
- Do **not** mutate Chris-owned `<HULDRA_HOME>\docs\OBJECTIVE.md`.
- Do **not** blindly copy the old LATCH Hermes tree into `ops\hermes`.

## 1) Proposed permanent directory tree

```
<HULDRA_HOME>\
  ops\
    hermes\                          # permanent Huldra Hermes *code* home
      README.md                      # what this instance is vs legacy LATCH
      source\                        # forked/adapted Hermes implementation
      config\                        # Huldra-specific config (secret-free examples + overlays)
      scripts\                       # launch / migration / helper scripts
      tests\                         # Huldra behavior + no-regression tests
      docs\                          # migration notes, architecture, diffs
  boards\
    huldra\                          # Hermes kanban / database / runtime state (OUTSIDE code tree)
  Results\                           # experiment evidence (already exists)
  docs\                              # scientific/project docs (Chris-owned OBJECTIVE.md)
  .hermes-live\                      # live status mirror (already exists; KEEP this path)
```

### Path decision vs request wording

| Requested | Decision | Why |
|---|---|---|
| `<HULDRA_HOME>\ops\hermes\` code home | **ACCEPT** as permanent target | Clear separation; scaffold created empty (no blind LATCH copy) |
| `<HULDRA_HOME>.hermes-live\` | **KEEP better equivalent** `<HULDRA_HOME>\.hermes-live\` | Already the live status SoT used by prep + operator mirror |
| `<HULDRA_HOME>\boards\huldra\` state | **ACCEPT** as *future* state home | Scaffolded empty; live state still under AppData `HERMES_HOME` |
| `<HULDRA_HOME>\Results\`, `<HULDRA_HOME>\docs\` | **KEEP** | Already outside code tree |

Staging (current, still valid until migration completes):

```
<HULDRA_HOME>\huldra-hermes-prep\          # git worktree / branch huldra-hermes-prep (staging source)
<HULDRA_HOME>\huldra-hermes-prep-home\     # isolated HERMES_HOME for offline/smoke only
```

## 2) Source-of-truth locations found (classified)

| Role | Path | Classification |
|---|---|---|
| **Live Hermes code (authoritative)** | `<LIVE_HERMES_INSTALL>` @ `3a980a431b28633a5b79c462f654dc100dc1c598` (`main`, hermes-agent 0.21.0) | LIVE SoT — do not mutate |
| **Live HERMES_HOME** | `<LIVE_HERMES_HOME>` | LIVE overlays/config/state — do not mutate |
| **Live process** | `hermes.exe gateway run` from live venv under that tree | LIVE — leave running |
| **Huldra prep worktree (staging)** | `<HULDRA_HOME>\huldra-hermes-prep` branch `huldra-hermes-prep` tip `84a810b0c315ef9d9c81e0b70b79b7617838b79d` | FORK staging (reusable core + Huldra guards/docs) |
| **Prep home (isolated)** | `<HULDRA_HOME>\huldra-hermes-prep-home\` | Sanitized config only; no real `.env` |
| **Status mirror** | `<HULDRA_HOME>\.hermes-live\` | Huldra convention already in use |
| **Results / docs** | `<HULDRA_HOME>\Results\`, `<HULDRA_HOME>\docs\` | Outside code tree (correct) |
| **Upstream remote** | `https://github.com/NousResearch/hermes-agent.git` | Reference only; local live is **4863 commits behind** origin — do not fast-forward live blindly |
| **LATCH workspace cwd (baggage)** | `<LEGACY_WORKSPACE>` (+ Drive `<LEGACY_DRIVE_PATH>`) | REMOVE-LATCH — never default for Huldra |
| **Permanent code home** | `<HULDRA_HOME>\ops\hermes\` | **TARGET** — scaffolded empty; not yet populated with classified source |

Evidence already recorded in `HULDRA_HERMES_PREP_REPORT.md`, `HULDRA_FORK_AUDIT.md`, `LATCH_BAGGAGE_QUARANTINE.md`.

## 3) Migration map (classified copy — not blind tree clone)

| From | To (permanent) | Action |
|---|---|---|
| Prep worktree core (`agent/`, `gateway/`, `tools/`, `run_agent.py`, …) | `ops\hermes\source\` | **KEEP** — move/repoint git worktree when ready; preserve history |
| `huldra_prep/`, `huldra_routing.py`, Huldra docs/tests | stay in source tree; also mirror layout/migration docs into `ops\hermes\docs\` | **HULDRA-ADAPT** already present in staging |
| Prep-home `config.yaml` (sanitized) + `huldra_prep/config.example.yaml` | `ops\hermes\config\` | **HULDRA-ADAPT** — secret-free only |
| Launch/helpers under prep that are Huldra-relevant | `ops\hermes\scripts\` | **Classify per file** — keep generic; rewrite LATCH cwd/channel assumptions |
| `tests/test_huldra_routing_guards.py` (+ future Huldra tests) | `ops\hermes\tests\` and/or keep under source `tests/` with pointer | **KEEP / extend** |
| Live `HERMES_HOME` state DBs / sessions / real `.env` / profiles | `boards\huldra\` (state only) — **never** into `ops\hermes\` | **Do not copy on prep**; cutover-only with explicit approval |
| Live LATCH profiles, Mighty/B1 caches, AGY-CLI-LATCH smokes | — | **DELETE/rewrite for Huldra** — quarantine list |
| Live status files | stay at `.hermes-live\` | **KEEP path** |

### Explicit non-copy list

- Live `state.db` / session DB
- Real `.env` / secrets
- `profiles/latch`, shun* fleet profiles as Huldra defaults
- Mighty/B1 / institutional_memory Latch pins
- AGY-CLI-LATCH smoke packages
- Anything that hardcodes `project Latch` or `#latch`

## 4) LATCH baggage inventory (summary)

Full detail: `LATCH_BAGGAGE_QUARANTINE.md` + `HULDRA_FORK_AUDIT.md`.

| Item | Verdict |
|---|---|
| `terminal.cwd` → project Latch | REMOVE / rewrite → `<HULDRA_HOME>` |
| Slack `#latch` / `C0BKT3BEP4H` | REMOVE as Huldra default |
| smart_policy "Project LATCH / Mighty" | REMOVE / rewrite Huldra + Ansel→Hermes |
| `profiles/latch` + shun* | QUARANTINE — do not activate |
| Project LATCH `HERMES.md` gates | QUARANTINE |
| Mighty/B1 caches under live HERMES_HOME | QUARANTINE |
| AGY-CLI-LATCH evidence packs | QUARANTINE |
| Skill/cron bodies with LATCH paths | UNKNOWN — scan before cutover |
| Kanban/dispatch/receipts/recovery engines | KEEP (generic) |

## 5) Test plan

Already green in staging:

- `pytest tests/test_huldra_routing_guards.py` → **7 passed** (via live venv Python + `PYTHONPATH=worktree`)

Add before declaring layout migration complete:

1. **Layout contract tests** — assert forbidden roots (`project Latch`, `#latch`) rejected; allowed roots (`<HULDRA_HOME>`, `#huldra`) accepted.
2. **Separation tests** — config/scripts under `ops\hermes\` must not write state into the code tree; state writes target `boards\huldra\` (or documented prep-home until cutover).
3. **No-regression** — existing routing guards still pass after any path repoint.
4. **Read-only live invariants** — script checks live HEAD still `3a980a431b…`, live cwd still Latch until cutover, `OBJECTIVE.md` mtime unchanged by Hermes prep tooling.
5. **Do not** start live gateway or install into live venv as part of layout work.

## 6) Diff / PR-style changes (this latch)

Additive only (prep + Huldra disk scaffold):

1. Add `HULDRA_HERMES_LAYOUT.md` (this file) to staging worktree.
2. Update `HERMES_HULDRA.md` Paths section → permanent home `<HULDRA_HOME>\ops\hermes\` + keep staging pointers.
3. Scaffold empty permanent tree:
   - `<HULDRA_HOME>\ops\hermes\{source,config,scripts,tests,docs}\`
   - `<HULDRA_HOME>\ops\hermes\README.md` (instance identity)
   - placeholders explaining **not yet populated** — source remains in `huldra-hermes-prep` until classified migration
4. Scaffold `<HULDRA_HOME>\boards\huldra\` (empty state home; no DB copy).
5. Commit on `huldra-hermes-prep` only. **No push. No live main changes.**

## 7) Cutover checklist + rollback

### Cutover (Chris-approved only; NOT now)

1. Confirm layout scaffold + staging tests green.
2. Classified copy/repoint worktree → `ops\hermes\source\` (git worktree move or fresh worktree).
3. Place secret-free config under `ops\hermes\config\`; inject secrets out-of-band (not in git).
4. Point isolated `HERMES_HOME` / state at `boards\huldra\` (fresh DB or approved migration — never silent live DB steal).
5. Dual-run / shadow against `#huldra` only; `#latch` still forbidden.
6. Integrate routing guards into gateway startup.
7. Swap process only after: tests green, Slack allowlist verified, Ansel reanchor, Chris irreversible-action approval.
8. Update status writes to continue using `<HULDRA_HOME>\.hermes-live\`.
9. Leave live AppData tree intact until rollback window closes.

### Rollback

1. Stop any Huldra-pointed gateway (if started).
2. Resume live `hermes.exe gateway run` from the original AppData venv.
3. Restore `HERMES_HOME` to `<LIVE_HERMES_HOME>`.
4. Ignore `ops\hermes\` and `boards\huldra\` (leave as inert prep artifacts).
5. Staging branch `huldra-hermes-prep` remains disposable review artifact.
6. `OBJECTIVE.md` never needed rollback if never touched.

## CUTOVER READINESS

**Still NOT READY** — layout target documented + scaffolded; source not relocated; live operator unchanged.

**REVIEW READY** for the layout spec and scaffold only.
