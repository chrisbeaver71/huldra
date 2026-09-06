"""Huldra V1 Lightweight Durable State.

Provides:
- JSON-based state persistence outside the code tree
- Session state (active session ID, preferences, working directory)
- Memory entries (facts, context, user preferences)
- State directory management (never inside ops/hermes/)
- Clean read/write with corruption recovery

State directory defaults to ``$HULDRA_HOME/state/`` (outside code tree, outside live Hermes)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default state directory — outside code tree, outside live Hermes
DEFAULT_STATE_DIR = Path(
    os.environ.get("HULDRA_STATE_DIR")
    or (Path(os.environ.get("HULDRA_HOME") or Path.cwd()) / "state")
)


class StateStore:
    """JSON-backed durable state stored outside the code tree.

    Usage:
        store = StateStore()  # uses HULDRA_STATE_DIR or HULDRA_HOME/state/
        store.set("session.active_id", "abc-123")
        active = store.get("session.active_id")
    """

    def __init__(self, state_dir: Optional[Path] = None):
        self._state_dir = state_dir or DEFAULT_STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Any] = {}
        self._loaded = False

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state_file = self._state_dir / "huldra_state.json"
        if state_file.exists():
            try:
                self._cache = json.loads(
                    state_file.read_text(encoding="utf-8")
                )
                self._loaded = True
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Corrupt state file, starting fresh: %s", e)
                self._cache = {}
                self._loaded = True
        else:
            self._cache = {}
            self._loaded = True

    def _persist(self) -> None:
        state_file = self._state_dir / "huldra_state.json"
        try:
            state_file.write_text(
                json.dumps(self._cache, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to persist state: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by dotted key path (e.g. 'session.active_id')."""
        self._ensure_loaded()
        parts = key.split(".")
        current = self._cache
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def set(self, key: str, value: Any) -> None:
        """Set a value by dotted key path. Persists immediately."""
        self._ensure_loaded()
        parts = key.split(".")
        current = self._cache
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        self._persist()

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if the key existed."""
        self._ensure_loaded()
        parts = key.split(".")
        current = self._cache
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        if parts[-1] in current:
            del current[parts[-1]]
            self._persist()
            return True
        return False

    def keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        self._ensure_loaded()
        result = []
        self._collect_keys(self._cache, prefix, result)
        return result

    def _collect_keys(
        self, obj: Any, prefix: str, result: list[str]
    ) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(val, dict):
                    self._collect_keys(val, full_key, result)
                else:
                    result.append(full_key)

    def all(self) -> dict[str, Any]:
        """Return a copy of all state."""
        self._ensure_loaded()
        return dict(self._cache)

    def clear(self) -> None:
        """Clear all state."""
        self._cache = {}
        self._loaded = True
        self._persist()


class MemoryStore:
    """Lightweight memory: key-value facts persisted as a JSON file.

    Memory entries are stored outside the code tree, separate from
    the main state file, for easy inspection and backup.

    Each memory entry has: key, content, timestamp, tags.
    """

    def __init__(self, state_dir: Optional[Path] = None):
        self._state_dir = state_dir or DEFAULT_STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._memory_file = self._state_dir / "huldra_memory.json"
        self._entries: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._memory_file.exists():
            try:
                self._entries = json.loads(
                    self._memory_file.read_text(encoding="utf-8")
                )
                self._loaded = True
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Corrupt memory file, starting fresh: %s", e)
                self._entries = {}
                self._loaded = True
        else:
            self._entries = {}
            self._loaded = True

    def _persist(self) -> None:
        try:
            self._memory_file.write_text(
                json.dumps(self._entries, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to persist memory: %s", e)

    def remember(self, key: str, content: str, tags: Optional[list[str]] = None) -> None:
        """Store a memory entry."""
        self._ensure_loaded()
        self._entries[key] = {
            "content": content,
            "timestamp": time.time(),
            "tags": tags or [],
        }
        self._persist()

    def recall(self, key: str) -> Optional[str]:
        """Recall a memory entry's content."""
        self._ensure_loaded()
        entry = self._entries.get(key)
        if entry:
            return entry.get("content")
        return None

    def forget(self, key: str) -> bool:
        """Remove a memory entry."""
        self._ensure_loaded()
        if key in self._entries:
            del self._entries[key]
            self._persist()
            return True
        return False

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search memory entries by content or tags (case-insensitive substring)."""
        self._ensure_loaded()
        query_lower = query.lower()
        results = []
        for key, entry in self._entries.items():
            content = entry.get("content", "").lower()
            tags = [t.lower() for t in entry.get("tags", [])]
            if query_lower in content or any(query_lower in t for t in tags):
                results.append({"key": key, **entry})
        return results

    def list_all(self) -> dict[str, dict[str, Any]]:
        """Return all memory entries."""
        self._ensure_loaded()
        return dict(self._entries)

    def clear(self) -> None:
        """Clear all memory."""
        self._entries = {}
        self._loaded = True
        self._persist()
