"""Tests for the optional Huldra worker/sub-agent routing boundary."""
from __future__ import annotations

import pathlib
import sys
from pathlib import Path

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "source"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))


class TestWorkerEngine:
    def test_only_bounded_task_kinds_are_eligible(self):
        from huldra_worker import is_worker_task_eligible

        assert is_worker_task_eligible("json-conversion")
        assert is_worker_task_eligible("repo inspection")
        assert not is_worker_task_eligible("general chat")
        assert not is_worker_task_eligible("tool execution")

    def test_non_worker_route_stays_on_primary(self, tmp_path):
        from huldra_profiles import create_v1_default_catalog
        from huldra_worker import WorkerEngine

        engine = WorkerEngine(create_v1_default_catalog(), tmp_path)
        route = engine.route("general_chat")
        assert route.eligible is False
        assert route.available is False
        assert route.routed_to_worker is False
        assert route.profile_id is None

    def test_missing_assets_fail_closed_without_auto_download(self, tmp_path):
        from huldra_profiles import create_v1_default_catalog
        from huldra_worker import WorkerEngine

        engine = WorkerEngine(create_v1_default_catalog(), tmp_path)
        route = engine.route("json_conversion")
        assert route.eligible is True
        assert route.available is False
        assert "missing" in route.reason

    def test_staged_ling_routes_bounded_task_and_builds_command(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_worker import WorkerEngine

        root = Path(r"E:/Huldra")
        engine = WorkerEngine(create_v1_default_catalog(), root)
        ok, errors = engine.verify_assets(hash_artifacts=False)
        assert ok, errors

        route = engine.route("json-conversion", verify_hash=False)
        assert route.routed_to_worker
        assert route.profile_id == "ling30-tiny-worker"

        command = engine.build_server_command()
        assert command[0].endswith("llama-server.exe")
        assert command[1] == "--model"
        assert command[2].endswith("Ling-3.0-tiny-Q6_K_L.gguf")
        assert "--port" in command
        assert command[command.index("--port") + 1] == "8081"
        assert "--jinja" in command

    def test_payload_disables_thinking_by_default_for_bounded_work(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_worker import WorkerEngine

        engine = WorkerEngine(create_v1_default_catalog(), Path(r"E:/Huldra"))
        payload = engine.build_chat_payload(
            "json-conversion", "Convert the following key/value pairs to JSON: a=1"
        )
        assert payload["model"] == "Ling-3.0-tiny-Q6_K_L"
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert "worker_task_kind" not in payload  # task kind stays in WorkerRoute metadata
        assert payload["max_tokens"] == 512

    def test_worker_profile_cannot_be_selected_as_primary(self):
        from huldra_profiles import create_v1_default_catalog

        catalog = create_v1_default_catalog()
        assert [p.id for p in catalog.primary_profiles] == [
            "qwen36-35b-apex", "gemma4-e4b", "qwen38-27b"
        ]
        assert all(p.role == "user-facing" for p in catalog.primary_profiles)
        assert all(p.role == "worker" for p in catalog.worker_profiles)
