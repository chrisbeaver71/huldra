# Attribution — Huldra Hermes V1

## Upstream

This product tree is derived from **Hermes Agent** by [Nous Research](https://github.com/NousResearch/hermes-agent).

- Upstream repository: https://github.com/NousResearch/hermes-agent
- Upstream license: MIT (see `LICENSE` and `source/LICENSE`)
- Reference live checkout (do not mutate from product scripts): `%LOCALAPPDATA%\hermes\hermes-agent` @ `3a980a431b` (main)
- Staging worktree: `<HULDRA_HOME>\huldra-hermes-prep` branch `huldra-hermes-prep`

## Huldra adaptations

Project Huldra additions under this tree include:

- `source/huldra_prep/` — path/channel routing guards
- `config/huldra.overlay.yaml`, `config/.env.huldra.example` — secret-free Huldra defaults
- `scripts/bootstrap-huldra.ps1`, `launch-huldra.ps1`, `huldra-doctor.ps1`, `smoke-huldra.ps1`
- `docs/HERMES_HULDRA.md`, `HULDRA_*`, `LATCH_BAGGAGE_QUARANTINE.md`

Huldra product notes do not alter the upstream MIT grant. Retain Nous Research copyright notices when redistributing.

## Quarantine

Project LATCH defaults (`#latch`, `profiles/latch`, Project LATCH cwd) are **not** product defaults. Mentions in quarantine docs are intentional.
