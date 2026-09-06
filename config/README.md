# Huldra Hermes config (secret-free)

| File | Purpose |
|------|---------|
| `config.example.yaml` | Product defaults: cwd $env:HULDRA_HOME, #huldra, boards/status paths |
| `huldra.overlay.yaml` | Same overlay for copy into a Huldra HERMES_HOME |
| `.env.huldra.example` | Trimmed env template (no secrets) |
| `.env.example` | Full upstream Hermes env template (placeholders only) |
| `cli-config.yaml.example` | Upstream CLI example |

Do not place real `.env`, `state.db`, or live secrets here.
For isolated smoke, use `$env:HULDRA_HOME\huldra-hermes-prep-home\`.
