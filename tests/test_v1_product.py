"""
V1 Product Integration Tests for Huldra.

Focused tests for all V1 product features:
- Backend abstraction (health, config, chat completion)
- Chat session (transcript, dedup, error handling, streaming)
- Tool registry (schema, validation, dispatch)
- File context (allowlists, deny patterns)
- State/memory (persistence, search, corruption recovery)
- Status tracker (components, tool stats, shutdown)

Run: python -m pytest tests/test_v1_product.py -v
"""
import json
import os
import pathlib
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure source/ is on the path for imports
_HERE = pathlib.Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "source"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))


# ============================================================================
# Backend Tests
# ============================================================================

class TestBackend:
    """Test LocalModelBackend, BackendConfig, health checking."""

    def test_backend_config_defaults(self):
        from backend import BackendConfig
        cfg = BackendConfig(name="test", base_url="http://localhost:8080", default_model="m")
        assert cfg.name == "test"
        assert cfg.base_url == "http://localhost:8080"
        assert cfg.default_model == "m"
        assert cfg.api_key_env is None
        assert cfg.api_key is None
        assert cfg.timeout_seconds == 30.0

    def test_backend_config_api_key_direct(self):
        from backend import BackendConfig
        cfg = BackendConfig(name="t", base_url="http://x", default_model="m", api_key="secret123")
        assert cfg.get_api_key() == "secret123"

    def test_backend_config_api_key_env(self):
        from backend import BackendConfig
        cfg = BackendConfig(name="t", base_url="http://x", default_model="m", api_key_env="MY_TEST_KEY_99887")
        with patch.dict(os.environ, {"MY_TEST_KEY_99887": "env_value"}):
            assert cfg.get_api_key() == "env_value"
        assert cfg.get_api_key() is None

    def test_backend_config_urls(self):
        from backend import BackendConfig
        cfg = BackendConfig(name="t", base_url="http://localhost:8080/v1", default_model="m")
        assert cfg.chat_completions_url() == "http://localhost:8080/v1/chat/completions"
        assert cfg.models_url() == "http://localhost:8080/v1/v1/models"
        assert cfg.health_url() == "http://localhost:8080/v1/health"

    def test_backend_status_enum(self):
        from backend import BackendStatus
        assert BackendStatus.HEALTHY.value == "healthy"
        assert BackendStatus.UNREACHABLE.value == "unreachable"
        assert BackendStatus.DEGRADED.value == "degraded"
        assert BackendStatus.UNKNOWN.value == "unknown"

    def test_backend_health_dataclass(self):
        from backend import BackendHealth, BackendStatus
        h = BackendHealth(status=BackendStatus.HEALTHY, latency_ms=42.5)
        assert h.status == BackendStatus.HEALTHY
        assert h.latency_ms == 42.5
        assert h.checked_at > 0

    def test_backend_error_types(self):
        from backend import BackendError, BackendUnreachableError, BackendModelNotFoundError
        err = BackendError("test_backend", "something broke", recoverable=True)
        assert err.backend_name == "test_backend"
        assert err.recoverable is True
        assert "[test_backend]" in str(err)

        unreachable = BackendUnreachableError("test_backend", "connection refused")
        assert unreachable.recoverable is True
        assert "unreachable" in str(unreachable)

        model_err = BackendModelNotFoundError("test_backend", "missing-model", ["a", "b"])
        assert model_err.recoverable is False
        assert "missing-model" in str(model_err)

    def test_local_model_backend_init(self):
        from backend import BackendConfig, LocalModelBackend
        cfg = BackendConfig(name="test", base_url="http://localhost:8080", default_model="m")
        backend = LocalModelBackend(cfg)
        assert backend.name == "test"
        assert backend.is_healthy is False  # no health check yet

    def test_backend_health_check_unreachable(self):
        from backend import BackendConfig, BackendStatus, LocalModelBackend
        cfg = BackendConfig(
            name="test",
            base_url="http://127.0.0.1:19999",
            default_model="m",
            timeout_seconds=1.0,
        )
        backend = LocalModelBackend(cfg)
        health = backend.check_health(force=True)
        assert health.status == BackendStatus.UNREACHABLE
        assert health.error is not None

    def test_load_backend_from_config_file(self):
        from backend import load_backend_from_config
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text(json.dumps({
                "backend": {
                    "name": "local",
                    "base_url": "http://127.0.0.1:8080",
                    "default_model": "test-model",
                }
            }))
            backends = load_backend_from_config(str(cfg_path))
            assert len(backends) == 1
            assert backends[0].name == "local"
            assert backends[0].config.default_model == "test-model"

    def test_load_backend_from_config_multiple(self):
        from backend import load_backend_from_config
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text(json.dumps({
                "providers": {
                    "ollama": {
                        "base_url": "http://127.0.0.1:11434/v1",
                        "default_model": "hermes3:8b",
                    },
                    "llama": {
                        "base_url": "http://127.0.0.1:8080",
                        "default_model": "local-model",
                    },
                }
            }))
            backends = load_backend_from_config(str(cfg_path))
            assert len(backends) == 2
            names = [b.name for b in backends]
            assert "ollama" in names
            assert "llama" in names


# ============================================================================
# Chat Session Tests
# ============================================================================

class TestChatSession:
    """Test Transcript, ChatMessage, ChatSession."""

    def test_chat_message_hash_deterministic(self):
        from huldra_chat import ChatMessage
        m1 = ChatMessage(role="user", content="hello")
        m2 = ChatMessage(role="user", content="hello")
        assert m1.message_hash == m2.message_hash

    def test_chat_message_different_content_different_hash(self):
        from huldra_chat import ChatMessage
        m1 = ChatMessage(role="user", content="hello")
        m2 = ChatMessage(role="user", content="world")
        assert m1.message_hash != m2.message_hash

    def test_chat_message_serialization(self):
        from huldra_chat import ChatMessage
        m = ChatMessage(role="assistant", content="Hi there", metadata={"source": "test"})
        d = m.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there"
        assert d["metadata"]["source"] == "test"
        m2 = ChatMessage.from_dict(d)
        assert m2.role == "assistant"
        assert m2.content == "Hi there"

    def test_transcript_dedup(self):
        from huldra_chat import Transcript
        t = Transcript()
        t.add("user", "hello")
        t.add("user", "hello")  # duplicate
        assert t.length == 1  # only one message

    def test_transcript_dedup_different_messages(self):
        from huldra_chat import Transcript
        t = Transcript()
        t.add("user", "hello")
        t.add("user", "world")
        assert t.length == 2

    def test_transcript_api_messages(self):
        from huldra_chat import Transcript
        t = Transcript()
        t.add("system", "You are helpful.")
        t.add("user", "Hi")
        t.add("assistant", "Hello!")
        msgs = t.get_api_messages()
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_transcript_persistence(self):
        from huldra_chat import Transcript
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "transcript.json"
            t1 = Transcript(persist_path=path)
            t1.add("user", "persist me")
            assert path.exists()

            # Load into new Transcript
            t2 = Transcript(persist_path=path)
            assert t2.length == 1
            assert t2.messages[0].content == "persist me"

    def test_transcript_clear(self):
        from huldra_chat import Transcript
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "transcript.json"
            t = Transcript(persist_path=path)
            t.add("user", "msg")
            assert t.length == 1
            t.clear()
            assert t.length == 0
            assert not path.exists()

    def test_chat_session_send(self):
        from backend import BackendConfig, LocalModelBackend
        from huldra_chat import ChatSession

        cfg = BackendConfig(name="mock", base_url="http://localhost:1", default_model="m")
        backend = LocalModelBackend(cfg)

        # Mock the chat_completion to return a fake response
        backend.chat_completion = MagicMock(return_value={
            "choices": [{"message": {"content": "Hello from mock!"}}]
        })

        session = ChatSession(backend, system_prompt="Test prompt")
        reply = session.send("Hi there")
        assert reply == "Hello from mock!"
        assert session.turn_count == 1
        assert session.error_count == 0

    def test_chat_session_error_tracking(self):
        from backend import BackendConfig, BackendError, LocalModelBackend
        from huldra_chat import ChatSession

        cfg = BackendConfig(name="mock", base_url="http://localhost:1", default_model="m")
        backend = LocalModelBackend(cfg)

        # Mock to raise a non-recoverable error
        backend.chat_completion = MagicMock(
            side_effect=BackendError("mock", "test error", recoverable=False)
        )

        session = ChatSession(backend, max_retries=0)
        with pytest.raises(BackendError):
            session.send("trigger error")
        assert session.error_count == 1
        assert "test error" in session.last_error

    def test_chat_session_health_check(self):
        from backend import BackendConfig, BackendStatus, LocalModelBackend
        from huldra_chat import ChatSession

        cfg = BackendConfig(
            name="mock",
            base_url="http://127.0.0.1:19999",
            default_model="m",
            timeout_seconds=1.0,
        )
        backend = LocalModelBackend(cfg)
        session = ChatSession(backend)
        status = session.health_check()
        assert status["backend"] == "mock"
        assert status["status"] == "unreachable"

    def test_chat_session_reset(self):
        from backend import BackendConfig, LocalModelBackend
        from huldra_chat import ChatSession

        cfg = BackendConfig(name="mock", base_url="http://localhost:1", default_model="m")
        backend = LocalModelBackend(cfg)
        backend.chat_completion = MagicMock(return_value={
            "choices": [{"message": {"content": "reply"}}]
        })

        session = ChatSession(backend)
        session.send("hi")
        assert session.turn_count == 1
        session.reset()
        assert session.turn_count == 0
        assert session.error_count == 0
        assert session._transcript.length == 1  # just the system prompt


# ============================================================================
# Tool Registry Tests
# ============================================================================

class TestToolRegistry:
    """Test ToolRegistry, ToolSchema, tool dispatch."""

    def test_tool_schema_openai_format(self):
        from huldra_tools import ToolSchema
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        )
        oai = schema.to_openai_tool()
        assert oai["type"] == "function"
        assert oai["function"]["name"] == "test_tool"
        assert "x" in oai["function"]["parameters"]["properties"]

    def test_tool_schema_validation_missing_required(self):
        from huldra_tools import ToolSchema
        schema = ToolSchema(
            name="test",
            description="t",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
            },
        )
        errors = schema.validate_args({})
        assert len(errors) == 1
        assert "Missing required" in errors[0]

    def test_tool_schema_validation_type_mismatch(self):
        from huldra_tools import ToolSchema
        schema = ToolSchema(
            name="test",
            description="t",
            parameters={
                "type": "object",
                "properties": {"n": {"type": "integer"}},
            },
        )
        errors = schema.validate_args({"n": "not_a_number"})
        assert len(errors) == 1
        assert "expected type" in errors[0]

    def test_tool_schema_validation_valid(self):
        from huldra_tools import ToolSchema
        schema = ToolSchema(
            name="test",
            description="t",
            parameters={
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "required": ["n"],
            },
        )
        errors = schema.validate_args({"n": 42})
        assert errors == []

    def test_registry_register_and_get(self):
        from huldra_tools import ToolRegistry
        reg = ToolRegistry()
        reg.register_simple("foo", "A foo tool", {"type": "object", "properties": {}})
        assert reg.has("foo")
        assert not reg.has("bar")
        assert "foo" in reg.get_names()

    def test_registry_get_schemas(self):
        from huldra_tools import ToolRegistry
        reg = ToolRegistry()
        reg.register_simple("a", "tool a", {"type": "object", "properties": {}})
        reg.register_simple("b", "tool b", {"type": "object", "properties": {}})
        schemas = reg.get_schemas()
        assert len(schemas) == 2
        names = [s["function"]["name"] for s in schemas]
        assert "a" in names
        assert "b" in names

    def test_registry_validate_tool_call(self):
        from huldra_tools import ToolRegistry
        reg = ToolRegistry()
        reg.register_simple(
            "echo",
            "echo tool",
            {
                "type": "object",
                "properties": {"msg": {"type": "string"}},
                "required": ["msg"],
            },
        )
        errors = reg.validate_tool_call("echo", {"msg": "hi"})
        assert errors == []
        errors = reg.validate_tool_call("echo", {})
        assert len(errors) == 1
        errors = reg.validate_tool_call("nonexistent", {})
        assert len(errors) == 1

    def test_registry_execute_tool(self):
        from huldra_tools import ToolRegistry
        reg = ToolRegistry()
        reg.register_simple(
            "add",
            "add two numbers",
            {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
            handler=lambda a, b: a + b,
        )
        result = reg.execute_tool("add", {"a": 3, "b": 4})
        assert result["success"] is True
        assert result["result"] == 7

    def test_registry_execute_tool_no_handler(self):
        from huldra_tools import ToolRegistry
        reg = ToolRegistry()
        reg.register_simple("nohandler", "no handler", {"type": "object", "properties": {}})
        result = reg.execute_tool("nohandler", {})
        assert result["success"] is False
        assert "no handler" in result["error"]

    def test_extract_tool_calls_from_response(self):
        from huldra_tools import extract_tool_calls_from_response
        response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "test_tool",
                            "arguments": '{"x": "hello"}',
                        },
                    }]
                }
            }]
        }
        calls = extract_tool_calls_from_response(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "test_tool"
        assert calls[0]["arguments"]["x"] == "hello"

    def test_extract_tool_calls_empty_response(self):
        from huldra_tools import extract_tool_calls_from_response
        calls = extract_tool_calls_from_response({})
        assert calls == []

    def test_register_v1_tools(self):
        from huldra_tools import ToolRegistry, register_v1_tools
        reg = ToolRegistry()
        register_v1_tools(reg)
        names = reg.get_names()
        assert "read_file" in names
        assert "write_file" in names
        assert "search_files" in names
        assert "terminal" in names
        assert "patch" in names
        assert len(names) == 5

    def test_tool_json_string_arguments(self):
        from huldra_tools import ToolSchema
        schema = ToolSchema(
            name="test",
            description="t",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        )
        # validate_args should handle JSON string args
        errors = schema.validate_args({"x": "hello"})
        assert errors == []


# ============================================================================
# File Context Tests
# ============================================================================

class TestFileContext:
    """Test PathGuard, FileAccessError, FileContext."""

    def test_path_guard_allows_huldra(self):
        from huldra_file_context import PathGuard
        guard = PathGuard()
        p = guard.validate("E:/Huldra/ops/hermes/backend.py")
        assert "backend.py" in str(p)

    def test_path_guard_denies_latch(self):
        from huldra_file_context import PathGuard, FileAccessError
        guard = PathGuard()
        with pytest.raises(FileAccessError):
            guard.validate("C:/Users/generic/project Latch/HERMES.md")

    def test_path_guard_denies_env_files(self):
        from huldra_file_context import PathGuard, FileAccessError
        guard = PathGuard()
        with pytest.raises(FileAccessError):
            guard.validate("E:/Huldra/.env")
        with pytest.raises(FileAccessError):
            guard.validate("E:/Huldra/config/secret.db")

    def test_path_guard_is_allowed(self):
        from huldra_file_context import PathGuard
        guard = PathGuard()
        assert guard.is_allowed("E:/Huldra/ops/hermes/source/backend.py")
        assert not guard.is_allowed("C:/Windows/System32/cmd.exe")

    def test_path_guard_add_remove_root(self):
        from huldra_file_context import PathGuard
        guard = PathGuard()
        guard.add_allowed_root("D:/extra")
        # On Windows, Path normalizes to backslash; compare resolved form
        resolved = str(Path("D:/extra"))
        assert resolved in guard.allowed_roots
        guard.remove_allowed_root("D:/extra")
        assert resolved not in guard.allowed_roots

    def test_file_context_read_write(self):
        from huldra_file_context import FileContext, PathGuard
        with tempfile.TemporaryDirectory() as td:
            guard = PathGuard(allowed_roots=[td])
            ctx = FileContext(guard)
            ctx.write_file(os.path.join(td, "test.txt"), "hello world")
            content = ctx.read_file(os.path.join(td, "test.txt"))
            assert content == "hello world"

    def test_file_context_file_exists(self):
        from huldra_file_context import FileContext, PathGuard
        with tempfile.TemporaryDirectory() as td:
            guard = PathGuard(allowed_roots=[td])
            ctx = FileContext(guard)
            path = os.path.join(td, "exists.txt")
            assert not ctx.file_exists(path)
            ctx.write_file(path, "content")
            assert ctx.file_exists(path)

    def test_file_context_search(self):
        from huldra_file_context import FileContext, PathGuard
        with tempfile.TemporaryDirectory() as td:
            guard = PathGuard(allowed_roots=[td])
            ctx = FileContext(guard)
            ctx.write_file(os.path.join(td, "a.py"), "print('a')")
            ctx.write_file(os.path.join(td, "b.txt"), "b text")
            results = ctx.search_files("*.py", td)
            assert len(results) == 1
            assert results[0].endswith("a.py")

    def test_file_context_desktop_context(self):
        from huldra_file_context import FileContext
        ctx = FileContext()
        dc = ctx.get_desktop_context()
        assert "cwd" in dc
        assert "platform" in dc
        assert "huldra_root" in dc

    def test_denied_pattern_matching(self):
        from huldra_file_context import PathGuard
        guard = PathGuard()
        assert guard._matches_pattern("test.env", "*.env")
        assert guard._matches_pattern("data.db", "*.db")
        assert guard._matches_pattern("secret.key", "*.key")
        assert not guard._matches_pattern("readme.md", "*.env")
        assert guard._matches_pattern("hello.txt", "hello*")
        assert not guard._matches_pattern("goodbye.txt", "hello*")


# ============================================================================
# State/Memory Tests
# ============================================================================

class TestStateAndMemory:
    """Test StateStore, MemoryStore persistence and search."""

    def test_state_store_set_get(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(state_dir=Path(td))
            store.set("session.active_id", "abc-123")
            assert store.get("session.active_id") == "abc-123"
            assert store.get("session.missing", "default") == "default"

    def test_state_store_nested_keys(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(state_dir=Path(td))
            store.set("a.b.c", 42)
            assert store.get("a.b.c") == 42
            assert store.get("a.b") == {"c": 42}

    def test_state_store_delete(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(state_dir=Path(td))
            store.set("x", 1)
            assert store.delete("x") is True
            assert store.get("x") is None
            assert store.delete("x") is False

    def test_state_store_persistence(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            s1 = StateStore(state_dir=Path(td))
            s1.set("persist_key", "persist_value")
            s2 = StateStore(state_dir=Path(td))
            assert s2.get("persist_key") == "persist_value"

    def test_state_store_corrupt_recovery(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            # Write corrupt JSON
            state_file = Path(td) / "huldra_state.json"
            state_file.write_text("NOT VALID JSON {{{")
            store = StateStore(state_dir=Path(td))
            # Should start fresh without crashing
            assert store.get("anything") is None
            store.set("new_key", "new_value")
            assert store.get("new_key") == "new_value"

    def test_state_store_keys(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(state_dir=Path(td))
            store.set("a.x", 1)
            store.set("a.y", 2)
            store.set("b.z", 3)
            keys = store.keys()
            assert "a.x" in keys
            assert "a.y" in keys
            assert "b.z" in keys

    def test_state_store_clear(self):
        from huldra_state import StateStore
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(state_dir=Path(td))
            store.set("x", 1)
            store.clear()
            assert store.get("x") is None

    def test_memory_store_remember_recall(self):
        from huldra_state import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            mem = MemoryStore(state_dir=Path(td))
            mem.remember("fact1", "The sky is blue", tags=["nature"])
            assert mem.recall("fact1") == "The sky is blue"
            assert mem.recall("nonexistent") is None

    def test_memory_store_forget(self):
        from huldra_state import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            mem = MemoryStore(state_dir=Path(td))
            mem.remember("tmp", "temporary")
            assert mem.forget("tmp") is True
            assert mem.recall("tmp") is None
            assert mem.forget("tmp") is False

    def test_memory_store_search(self):
        from huldra_state import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            mem = MemoryStore(state_dir=Path(td))
            mem.remember("weather", "It is sunny today", tags=["weather"])
            mem.remember("food", "Pizza for lunch", tags=["food"])
            results = mem.search("sunny")
            assert len(results) == 1
            assert results[0]["key"] == "weather"
            results = mem.search("weather")
            assert len(results) == 1  # matches tag
            results = mem.search("nonexistent")
            assert len(results) == 0

    def test_memory_store_persistence(self):
        from huldra_state import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            m1 = MemoryStore(state_dir=Path(td))
            m1.remember("k", "v", tags=["t"])
            m2 = MemoryStore(state_dir=Path(td))
            assert m2.recall("k") == "v"

    def test_memory_store_corrupt_recovery(self):
        from huldra_state import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            mem_file = Path(td) / "huldra_memory.json"
            mem_file.write_text("BROKEN {{{")
            mem = MemoryStore(state_dir=Path(td))
            # Should not crash
            assert mem.recall("anything") is None
            mem.remember("new", "fresh")
            assert mem.recall("new") == "fresh"


# ============================================================================
# Status Tracker Tests
# ============================================================================

class TestStatusTracker:
    """Test StatusTracker, ComponentReport, ToolCallRecord."""

    def test_status_tracker_components(self):
        from huldra_status import StatusTracker, ComponentStatus
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            tracker.update_component("backend", ComponentStatus.HEALTHY, "all good")
            comp = tracker.get_component("backend")
            assert comp is not None
            assert comp.status == ComponentStatus.HEALTHY
            assert comp.detail == "all good"

    def test_status_tracker_tool_calls(self):
        from huldra_status import StatusTracker, ToolCallRecord
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            tracker.record_tool_call(ToolCallRecord("read_file", True))
            tracker.record_tool_call(ToolCallRecord("write_file", False, "permission denied"))
            stats = tracker.get_tool_stats()
            assert stats["total"] == 2
            assert stats["success"] == 1
            assert stats["failure"] == 1
            assert stats["success_rate"] == 0.5

    def test_status_tracker_turns(self):
        from huldra_status import StatusTracker
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            tracker.record_turn(True)
            tracker.record_turn(True)
            tracker.record_turn(False, "backend error")
            summary = tracker.get_summary()
            assert summary["session"]["turns"] == 3
            assert summary["session"]["errors"] == 1
            assert summary["session"]["last_error"] == "backend error"

    def test_status_tracker_shutdown(self):
        from huldra_status import StatusTracker
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            assert not tracker.is_shutting_down
            tracker.request_shutdown()
            assert tracker.is_shutting_down
            tracker.complete_shutdown()
            assert not tracker.is_shutting_down

    def test_status_tracker_save_snapshot(self):
        from huldra_status import StatusTracker, ComponentStatus
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            tracker.update_component("backend", ComponentStatus.HEALTHY)
            path = tracker.save_snapshot()
            assert path.exists()
            data = json.loads(path.read_text())
            assert "components" in data
            assert "backend" in data["components"]

    def test_status_tracker_uptime(self):
        from huldra_status import StatusTracker
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            assert tracker.uptime_seconds >= 0

    def test_status_tracker_tool_stats_empty(self):
        from huldra_status import StatusTracker
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            stats = tracker.get_tool_stats()
            assert stats["total"] == 0
            assert stats["success_rate"] == 0.0

    def test_status_tracker_tool_calls_limit(self):
        from huldra_status import StatusTracker, ToolCallRecord
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            for i in range(120):
                tracker.record_tool_call(ToolCallRecord(f"tool_{i}", True))
            stats = tracker.get_tool_stats()
            assert stats["total"] == 100  # capped at 100

    def test_status_tracker_summary(self):
        from huldra_status import StatusTracker, ComponentStatus, ToolCallRecord
        with tempfile.TemporaryDirectory() as td:
            tracker = StatusTracker(status_dir=Path(td))
            tracker.update_component("backend", ComponentStatus.HEALTHY, latency_ms=5.2)
            tracker.record_tool_call(ToolCallRecord("read_file", True))
            tracker.record_turn(True)
            summary = tracker.get_summary()
            assert "uptime_seconds" in summary
            assert "components" in summary
            assert "session" in summary
            assert "tools" in summary
            assert "shutdown" in summary
