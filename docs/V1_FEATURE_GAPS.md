# Huldra V1 feature gaps (Hermes-derived) — zero-GPU picks

Identified during V1 engineering latch. Implemented what fits without GPU/process frameworks.

| Gap | Value | Status |
|-----|-------|--------|
| Clear first-run README + bootstrap errors | Operators cannot find the product path vs live Hermes | **Done** — ops README + bootstrap-huldra.ps1 refuse live HERMES_HOME |
| `huldra status` / doctor without GPU | Path/config confidence before spending model tokens | **Done** — huldra-doctor.ps1 |
| Better Windows path/channel guard messaging | Silent LATCH inheritance is the #1 cutover risk | **Done** — clearer PermissionError text + is_huldra_path |
| Secret-free trimmed `.env.example` for Huldra | Upstream `.env.example` is huge and noisy | **Done** — `.env.huldra.example` |
| One-command smoke | Regression gate without full suite | **Done** — smoke-huldra.ps1 |
| Architecture / operator one-pager | Onboarding without reading fork audit | **Done** — docs/OPERATOR.md |

## Still open (not implemented; may need Chris / secrets / GPU)

1. Provision real Slack + LLM secrets into prep-home `.env` (Chris-owned)
2. Point live gateway HERMES_HOME / cwd at Huldra (cutover auth)
3. Kanban boards DB init under `E:\Huldra\boards\huldra` with real state (no live state.db copy)
4. End-to-end Slack reply in #huldra from Huldra-pointed gateway
5. Optional: wire `hermes doctor` subcommand to call Huldra routing checks natively
