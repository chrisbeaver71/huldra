# LATCH Baggage Quarantine

Intentional non-carry-forward list for the Huldra Hermes prep fork.
These assumptions live in the *live* Hermes operator / Project LATCH workspace
and must **not** become Huldra defaults.

## Quarantined (REMOVE-LATCH / do not port)

1. **Terminal cwd** `<LEGACY_WORKSPACE>` (also Drive path `<LEGACY_DRIVE_PATH>`).
2. **Slack `#latch` / `C0BKT3BEP4H`** as coordination default or free-response surface for Huldra work.
3. **`approvals.smart_policy` Project LATCH / Mighty wording** (evidence/ledger gate framing tied to LATCH).
4. **Profile `profiles/latch`** (and related shun* fleet profiles) as active HERMES_HOME profile for Huldra.
5. **Project LATCH `HERMES.md` gates** (workspace-local operator contract under project Latch).
6. **Mighty / B1 institutional gates** and LATCH-pinned `institutional_memory` / Mighty card cache artifacts under live `HERMES_HOME\cache\mighty-*`.
7. **AGY LATCH backend smoke packages** under live `agy-smoke-evidence\AGY-CLI-LATCH-*` (evidence of old operator, not Huldra product).
8. **Any overlay that hardcodes `project Latch` paths** in skills, cron bodies, or blocked-script caches.

## Kept as capability concepts (not LATCH-specific)

- Kanban dispatch / task decomposition
- Process/run coordination
- Receipts / evidence trails
- Recovery / reclaim / session DB recovery patterns
- Status reporting
- Duplicate-run prevention / admission guards
- Bounded integration (approvals, deny lists, tirith)

## Huldra replacements

| LATCH default | Huldra prep default |
|---|---|
| `<LEGACY_WORKSPACE>` | `<HULDRA_HOME>` |
| `#latch` / `C0BKT3BEP4H` | `#huldra` / `C0BKR5LEYV8` |
| LATCH/Mighty smart_policy | Huldra smart_policy + Ansel→Hermes authority |
| LATCH evidence/ledger paths | `<HULDRA_HOME>/Results`, `<HULDRA_HOME>/evidence`, status via `<HULDRA_HOME>/.hermes-live` |

## Explicit non-goals of this prep

- Do not migrate live `state.db` / sessions into prep-home.
- Do not copy real `.env`.
- Do not cut over the live `hermes.exe gateway run` process.
