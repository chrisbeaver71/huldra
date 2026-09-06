# Huldra Hermes V1

A self-contained, isolated fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research, MIT License) adapted for the Project Huldra operating environment.

**Status:** permanent tree under `$env:HULDRA_HOME\ops\hermes` is populated (`source\`, `config\`, `scripts\`, `tests\`, `docs\`). Live Hermes remains at `$env:LOCALAPPDATA\hermes` and is untouched by these scripts.

## What this is

- **Hermes Agent core**: agent loop, gateway, session primitives, toolsets, kanban dispatch, receipts, recovery, status reporting
- **Huldra adaptations**: path/channel guards, secret-free config overlays, Windows bootstrap/doctor/smoke, operator docs
- **Profile-driven architecture**: versioned model catalog with 3 V1 profiles, hardware detection, and automatic recommendation
- **Permanent code tree**: publication-ready layout under `$env:HULDRA_HOME\ops\hermes`

## What this is NOT

- The live Hermes process (that remains at `$env:LOCALAPPDATA\hermes`)
- A LATCH workspace (LATCH baggage is quarantined -- see `docs/LATCH_BAGGAGE_QUARANTINE.md`)
- A live deployment (the public source repository is separate from local runtime state)

## Directory layout

```
$env:HULDRA_HOME\ops\hermes\
  README.md               <- this file
  LICENSE / ATTRIBUTION.md
  source\                 <- forked/adapted Hermes implementation (+ huldra_prep)
  config\                 <- Huldra secret-free overlays (.env.huldra.example, huldra.overlay.yaml)
  scripts\                <- bootstrap-huldra / launch-huldra / huldra-doctor / smoke-huldra / huldra-pointer + upstream
  tests\                  <- Huldra routing + V1 smoke + upstream suite
  docs\                   <- OPERATOR.md, architecture, rollback, baggage audit
```

## Quick start (Windows) -- Huldra product path

```powershell
$env:HULDRA_HOME = '<install-root>'   # replace with your local Huldra root
Set-Location "$env:HULDRA_HOME\ops\hermes"
.\scripts\bootstrap-huldra.ps1   # layout + prep-home seed (never live HERMES_HOME)
.\scripts\huldra-doctor.ps1      # zero-GPU path/config/routing checks
.\scripts\smoke-huldra.ps1       # one-command smoke (pytest + YAML + layout)
# Optional smoke launch (prep-home only):
.\scripts\launch-huldra.ps1
# Reversible local pointer activation (does not mutate live Hermes):
.\scripts\huldra-pointer.ps1 -Action activate -HuldraHome $env:HULDRA_HOME -PrepHome "$env:HULDRA_HOME\huldra-hermes-prep-home"
.\scripts\huldra-pointer.ps1 -Action rollback -HuldraHome $env:HULDRA_HOME
```

See `docs/OPERATOR.md` for the one-pager.

### Configure (secret-free)

```powershell
Copy-Item config\huldra.overlay.yaml "$env:HULDRA_HOME\huldra-hermes-prep-home\config.yaml"
Copy-Item config\.env.huldra.example "$env:HULDRA_HOME\huldra-hermes-prep-home\.env"
# Edit .env with real secrets locally -- never commit; never copy live .env into ops
```

Product defaults: cwd `$env:HULDRA_HOME`, Slack `#huldra` / `C0BKR5LEYV8`, boards `$env:HULDRA_HOME\boards\huldra`, status `$env:HULDRA_HOME\.hermes-live`.

### V1 Profiles

The profile-driven architecture provides three locked model profiles:

| Profile | Model | Quant | Runtime | Min VRAM | Min RAM |
|---------|-------|-------|---------|----------|---------|
| `qwen36-35b-apex` | Qwen 3.6 35B-A3B | APEX I-Compact Q4_K_M | ik_llama.cpp | 8 GB | 16 GB |
| `gemma4-e4b` | Gemma 4 E4B | Google QAT Q4_0 | llama.cpp | 4 GB | 8 GB |
| `qwen38-27b` | Qwen 3.8 27B | ggml-org Q4_K_M + MTP Q4_0 | llama.cpp (CUDA) | 8 GB | 16 GB |

Hardware detection (`huldra_hardware`) runs at first launch and recommends the best-fit profile. Manual override is available with clear fit/asset error messages. Qwen 3.8 catalog entries are tolerant of the asset handoff completing later but fail closed if the model is not verified installed.

See `source/huldra_profiles.py`, `source/huldra_hardware.py`, `source/huldra_recommender.py`.

### Upstream installers (optional)

```powershell
.\scripts\install.ps1
.\scripts\launch.cmd gateway
```

## Authority model

| Role | Responsibility |
|------|---------------|
| **Ansel** (ChatGPT) | Scientific/product intent, reanchor against OBJECTIVE |
| **Hermes** | Execution agent -- dispatch, decompose, run, recover, report |
| **Chris** | Approves irreversible / spend / deploy / external send |

## Quarantine

LATCH workspace defaults, `#latch` channel, Mighty/B1 gates, and `profiles/latch` are quarantined and must not become Huldra defaults. See `docs/LATCH_BAGGAGE_QUARANTINE.md` and `docs/HULDRA_FORK_AUDIT.md`.

## State (outside code tree)

All persistent state lives outside the code tree in a configured external directory (default: `$env:HULDRA_HOME`).

| Purpose | Configurable path |
|---------|------|
| Kanban/database/state | `$env:HULDRA_HOME\boards\huldra` |
| Live status mirror | `$env:HULDRA_HOME\.hermes-live` |
| Evidence/results | `$env:HULDRA_HOME\Results` |
| Science docs | `$env:HULDRA_HOME\docs` |

## Rollback

1. Stop any Huldra-pointed gateway
2. Resume the original live Hermes from `$env:LOCALAPPDATA\hermes`
3. Restore `HERMES_HOME` to `$env:LOCALAPPDATA\hermes`
4. Leave `ops\hermes\` and `boards\huldra\` as inert prep artifacts

See `docs/rollback.md`.

## License

MIT License -- Copyright (c) 2025 Nous Research. See `LICENSE` and `ATTRIBUTION.md`.

## Source attribution

Fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Upstream attribution and license preserved. Staging branch: `huldra-hermes-prep`.
