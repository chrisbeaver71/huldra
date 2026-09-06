# HERMES_HULDRA — Operating Stub (prep)

Huldra-native operator contract for the isolated fork at
`E:\Huldra\huldra-hermes-prep`. This is **not** live.

## Identity

- Code worktree: `E:\Huldra\huldra-hermes-prep` (branch `huldra-hermes-prep`)
- Prep home: `E:\Huldra\huldra-hermes-prep-home` (isolated; no live profiles)
- Live Hermes remains at `<LIVE_HERMES_HOME>` — do not mutate it from this stub

## Paths

- Workspace / cwd: `E:\Huldra`
- Results / receipts / evidence packages: `E:\Huldra\Results` (and `E:\Huldra\evidence` when used)
- Docs / objective: `E:\Huldra\docs` — **`OBJECTIVE.md` is Chris-owned; do not mutate**
- Live status mirror (read/write only under Huldra): `E:\Huldra\.hermes-live`
- Forbidden: `<LEGACY_WORKSPACE>`, `<LEGACY_DRIVE_PATH>`

## Coordination

- Channel: `#huldra` / `C0BKR5LEYV8`
- Forbidden channel: `#latch` / `C0BKT3BEP4H`
- Use `huldra_prep.huldra_routing` guards before path/channel-sensitive actions

## Authority

- **Ansel** (ChatGPT): scientific/product intent and reanchor against OBJECTIVE
- **Hermes**: execution agent — dispatch, decompose, run, recover, report
- **Chris**: approves irreversible / spend / deploy / external send

## Preserve capability concepts

Dispatch, task decomposition, process/run coordination, receipts/evidence,
recovery/reclaim, status reporting, duplicate-run prevention, bounded integration.

## Quarantine

See `LATCH_BAGGAGE_QUARANTINE.md`. No LATCH workspace default.

## Permanent layout target (2026-09-05)

Permanent code home (scaffold only until classified migration):

- `E:\Huldra\ops\hermes\` — code (`source`, `config`, `scripts`, `tests`, `docs`)
- `E:\Huldra\boards\huldra\` — kanban/database/state (outside code tree)
- Status mirror remains `E:\Huldra\.hermes-live\` (preferred over `E:\Huldra.hermes-live`)

See `HULDRA_HERMES_LAYOUT.md` for SoT table, migration map, baggage inventory, tests, and cutover/rollback.
Staging worktree/home above remain valid until that migration is explicitly approved.
