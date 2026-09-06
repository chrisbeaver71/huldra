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
