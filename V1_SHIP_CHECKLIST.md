# Huldra V1 Ship Checklist

Ship-blocking items for Huldra V1 local-assistant release.
Mark each item complete with a short evidence path or command.

## Backend Abstraction
- [x] Local model backend abstraction with health checking
  - Evidence: `source/backend.py` — LocalModelBackend, BackendConfig, check_health()
- [x] Secret-free configuration (API keys optional for local servers)
  - Evidence: `config/config.example.yaml`, `config/.env.huldra.example`
- [x] OpenAI-compatible endpoint path (llama-server, Ollama, vLLM)
  - Evidence: `backend.py:53-60` — chat_completions_url(), models_url(), health_url()

## Chat Session
- [x] Transcript continuity across turns
  - Evidence: `source/huldra_chat.py` — Transcript class with persistence
- [x] Duplicate/corrupt message detection
  - Evidence: `huldra_chat.py:71-81` — hash-based dedup in Transcript.add()
- [x] Clean error handling with retries
  - Evidence: `huldra_chat.py:167-210` — ChatSession.send() with BackendError handling
- [x] Streaming support
  - Evidence: `huldra_chat.py:212-231` — ChatSession.send_streaming()

## Tool Invocation
- [x] Tool schema registration with JSON Schema validation
  - Evidence: `source/huldra_tools.py` — ToolRegistry, ToolSchema
- [x] Argument validation before execution
  - Evidence: `huldra_tools.py:53-72` — ToolSchema.validate_args()
- [x] Structured output handling (tool call extraction)
  - Evidence: `huldra_tools.py:152-183` — extract_tool_calls_from_response()
- [x] Built-in V1 tool set (read_file, write_file, search, terminal, patch)
  - Evidence: `huldra_tools.py:190-278` — register_v1_tools()

## Files/Desktop-Context Boundary
- [x] Explicit allowlists for file access paths
  - Evidence: `source/huldra_file_context.py` — PathGuard with allowed_roots
- [x] Deny patterns for sensitive files (*.env, *.db, *.key)
  - Evidence: `huldra_file_context.py:36-42` — default denied_patterns
- [x] Path validation before any file operation
  - Evidence: `huldra_file_context.py:88-110` — PathGuard.validate()
- [x] No ambient filesystem access
  - Evidence: All file ops go through FileContext, which delegates to PathGuard

## Durable Memory/State
- [x] State stored outside code tree (configured external state directory)
  - Evidence: `source/huldra_state.py` — StateStore, MemoryStore
- [x] JSON-backed key-value state with dotted-path access
  - Evidence: `huldra_state.py:47-90` — StateStore.get/set/delete
- [x] Memory entries with tags and search
  - Evidence: `huldra_state.py:100-160` — MemoryStore.remember/recall/search
- [x] Corruption recovery (starts fresh on bad JSON)
  - Evidence: `huldra_state.py:59-63` — catch JSONDecodeError, start fresh

## Recovery/Status Visibility
- [x] Backend health status reporting
  - Evidence: `source/huldra_status.py` — StatusTracker, ComponentReport
- [x] Tool call failure tracking
  - Evidence: `huldra_status.py:93-100` — StatusTracker.record_tool_call()
- [x] Session status (turns, errors, last error)
  - Evidence: `huldra_status.py:102-108` — StatusTracker.record_turn()
- [x] Clean shutdown coordination
  - Evidence: `huldra_status.py:110-120` — request_shutdown/complete_shutdown
- [x] Status snapshot to disk
  - Evidence: `huldra_status.py:147-157` — save_snapshot()

## Windows Bootstrap/Launch
- [x] Native Windows launcher (launch.cmd)
  - Evidence: `scripts/launch.cmd` — finds venv, sets HERMES_HOME, dispatches
- [x] Bootstrap script (bootstrap-huldra.ps1)
  - Evidence: `scripts/bootstrap-huldra.ps1` — layout verification, directory creation
- [x] Huldra config overlay (huldra.overlay.yaml)
  - Evidence: `config/huldra.overlay.yaml` — Huldra-specific paths and settings
- [x] HERMES_HOME isolation (never mutates live Hermes)
  - Evidence: `launch.cmd:13` — `set "HERMES_HOME=%LOCALAPPDATA%\hermes-huldra"`

## No LATCH Coupling
- [x] No active LATCH defaults in config
  - Evidence: `tests/test_v1_smoke.py::TestNoLatchCoupling` — 4 tests pass
- [x] Routing guards reject LATCH paths
  - Evidence: `tests/test_v1_smoke.py::TestRoutingGuards` — 4 tests pass
- [x] No real secrets in examples
  - Evidence: `tests/test_v1_smoke.py::TestNoLatchCoupling::test_env_example_no_real_secrets`

## Tests
- [x] V1 smoke tests (layout, imports, guards)
  - Evidence: `tests/test_v1_smoke.py` — 18 tests, all pass
- [x] Backend abstraction tests
  - Evidence: `tests/test_v1_product.py::TestBackend`
- [x] Chat session tests (transcript, dedup, error handling)
  - Evidence: `tests/test_v1_product.py::TestChatSession`
- [x] Tool registry tests (schema, validation, dispatch)
  - Evidence: `tests/test_v1_product.py::TestToolRegistry`
- [x] File context tests (allowlist, deny patterns)
  - Evidence: `tests/test_v1_product.py::TestFileContext`
- [x] State/memory tests (persistence, search)
  - Evidence: `tests/test_v1_product.py::TestStateAndMemory`
- [x] Status tracker tests
  - Evidence: `tests/test_v1_product.py::TestStatusTracker`

## Profile-Driven Architecture
- [x] Versioned profile catalog with schema validation
  - Evidence: `source/huldra_profiles.py` — ProfileCatalog, Profile, ArtifactRef
- [x] Three V1 profiles (Qwen3.6-35B, Gemma 4 E4B, Qwen3.8-27B)
  - Evidence: `huldra_profiles.py:create_v1_default_catalog()` — 3 profiles
- [x] Profile artifact declarations (model, runtime, template, hash, license)
  - Evidence: `huldra_profiles.py:ArtifactRef` — source/revision/hash/license
- [x] Resource requirements per profile (disk, RAM, VRAM min/recommended)
  - Evidence: `huldra_profiles.py:ResourceRequirements`
- [x] Fallback/recovery configuration per profile
  - Evidence: `huldra_profiles.py:FallbackConfig` — fallback_profiles, retry, auto_download
- [x] Catalog save/load roundtrip and validation
  - Evidence: `tests/test_v1_profiles.py::TestProfileCatalog`

## Hardware Detection
- [x] Deterministic GPU/VRAM detection (nvidia-smi, WMI fallback)
  - Evidence: `source/huldra_hardware.py` — _detect_gpu_nvidia, _detect_gpu_wmi
- [x] System RAM detection (WMI, psutil, sysconf fallback)
  - Evidence: `huldra_hardware.py:_detect_ram()`
- [x] Storage detection at HULDRA_HOME
  - Evidence: `huldra_hardware.py:_detect_storage()`
- [x] Usable resources with reserved headroom (no benchmark inference)
  - Evidence: `huldra_hardware.py` — SYSTEM_RESERVED_* constants
- [x] Hardware profile save/load for caching
  - Evidence: `huldra_hardware.py:save_hardware_profile, load_hardware_profile`
- [x] Hardware detection tests
  - Evidence: `tests/test_v1_profiles.py::TestHardwareDetection`

## Recommender
- [x] Fit derivation from declared requirements + headroom
  - Evidence: `source/huldra_recommender.py` — check_requirements()
- [x] Fit levels: FULL, PARTIAL, INSUFFICIENT, UNKNOWN
  - Evidence: `huldra_recommender.py:FitLevel`
- [x] Supports ~8 GB VRAM / ~16 GB RAM minimum viable tier
  - Evidence: `tests/test_v1_profiles.py::test_8gb_vram_16gb_ram_minimal_tier`
- [x] Manual profile override with clear fit/asset errors
  - Evidence: `huldra_recommender.py:recommend_profiles(manual_override=...)`
- [x] Recommendation report formatting
  - Evidence: `huldra_recommender.py:format_recommendation_report()`
- [x] Recommender tests (sort, override, margin, all fit levels)
  - Evidence: `tests/test_v1_profiles.py::TestRecommender`
