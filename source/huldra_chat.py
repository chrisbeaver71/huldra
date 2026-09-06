"""Huldra V1 Chat Session — thin integration on top of LocalModelBackend.

Provides:
- Transcript continuity across turns (in-memory + optional file persistence)
- Clean error handling with structured BackendError types
- Duplicate/corrupt message detection and repair
- System prompt management
- History serialization for restart/reclaim
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend import (
    BackendConfig,
    BackendError,
    BackendStatus,
    BackendUnreachableError,
    LocalModelBackend,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """A single message in the transcript."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    message_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.message_hash:
            self.message_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = f"{self.role}:{self.content}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_hash": self.message_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", 0.0),
            message_hash=data.get("message_hash", ""),
            metadata=data.get("metadata", {}),
        )


class Transcript:
    """In-memory transcript with duplicate detection and persistence."""

    def __init__(self, persist_path: Optional[Path] = None):
        self._messages: list[ChatMessage] = []
        self._seen_hashes: set[str] = set()
        self._persist_path = persist_path
        if persist_path:
            self._load()

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    @property
    def length(self) -> int:
        return len(self._messages)

    def add(self, role: str, content: str, **metadata: Any) -> ChatMessage:
        """Add a message, rejecting duplicates."""
        msg = ChatMessage(role=role, content=content, metadata=metadata)
        if msg.message_hash in self._seen_hashes:
            logger.warning(
                "Duplicate message detected (hash=%s, role=%s), skipping",
                msg.message_hash,
                role,
            )
            return msg
        self._messages.append(msg)
        self._seen_hashes.add(msg.message_hash)
        if self._persist_path:
            self._save()
        return msg

    def get_api_messages(self) -> list[dict[str, str]]:
        """Return messages formatted for the OpenAI-compatible API."""
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def clear(self) -> None:
        self._messages.clear()
        self._seen_hashes.clear()
        if self._persist_path and self._persist_path.exists():
            self._persist_path.unlink()

    def _save(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = [m.to_dict() for m in self._messages]
            self._persist_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Failed to persist transcript: %s", e)

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for item in data:
                msg = ChatMessage.from_dict(item)
                if msg.message_hash not in self._seen_hashes:
                    self._messages.append(msg)
                    self._seen_hashes.add(msg.message_hash)
            logger.info(
                "Loaded %d messages from transcript at %s",
                len(self._messages),
                self._persist_path,
            )
        except Exception as e:
            logger.warning("Failed to load transcript from %s: %s", self._persist_path, e)


class ChatSession:
    """V1 chat session: transcript + backend + error handling.

    Usage:
        backend = LocalModelBackend(config)
        session = ChatSession(backend, system_prompt="You are Huldra.")
        reply = session.send("Hello!")
    """

    def __init__(
        self,
        backend: LocalModelBackend,
        system_prompt: str = "You are Huldra, a local AI assistant.",
        transcript_path: Optional[Path] = None,
        max_retries: int = 2,
    ):
        self._backend = backend
        self._system_prompt = system_prompt
        self._transcript = Transcript(persist_path=transcript_path)
        self._max_retries = max_retries
        self._turn_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        # Seed system prompt if transcript is empty
        if self._transcript.length == 0:
            self._transcript.add("system", system_prompt)

    @property
    def backend_healthy(self) -> bool:
        return self._backend.is_healthy

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def send(self, user_message: str, **kwargs: Any) -> str:
        """Send a user message and return the assistant response.

        Handles retries on transient backend errors.
        Raises BackendUnreachableError after max_retries.
        """
        self._transcript.add("user", user_message)
        self._turn_count += 1

        last_error: Optional[BackendError] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._backend.chat_completion(
                    messages=self._transcript.get_api_messages(),
                    stream=False,
                    **kwargs,
                )
                content = self._extract_content(response)
                self._transcript.add("assistant", content)
                self._last_error = None
                return content
            except BackendUnreachableError as e:
                last_error = e
                self._error_count += 1
                self._last_error = str(e)
                if attempt < self._max_retries:
                    logger.warning(
                        "Backend unreachable (attempt %d/%d): %s",
                        attempt + 1,
                        self._max_retries + 1,
                        e,
                    )
                    continue
                raise
            except BackendError as e:
                last_error = e
                self._error_count += 1
                self._last_error = str(e)
                if not e.recoverable or attempt >= self._max_retries:
                    raise
                logger.warning(
                    "Recoverable backend error (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )
                continue

        # Should not reach here, but defensive
        if last_error:
            raise last_error
        return ""

    def send_streaming(self, user_message: str, **kwargs: Any):
        """Send a user message and yield content deltas.

        Yields content chunks; caller should collect into full response.
        """
        self._transcript.add("user", user_message)
        self._turn_count += 1

        full_content = []
        try:
            for chunk in self._backend.chat_completion_stream(
                messages=self._transcript.get_api_messages(),
                **kwargs,
            ):
                full_content.append(chunk)
                yield chunk
            assembled = "".join(full_content)
            self._transcript.add("assistant", assembled)
            self._last_error = None
        except BackendError as e:
            self._error_count += 1
            self._last_error = str(e)
            raise

    def health_check(self) -> dict[str, Any]:
        """Check backend health and return status dict."""
        health = self._backend.check_health(force=True)
        return {
            "backend": self._backend.name,
            "status": health.status.value,
            "latency_ms": round(health.latency_ms, 1),
            "error": health.error,
            "turn_count": self._turn_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    def export_transcript(self) -> list[dict[str, Any]]:
        """Export full transcript as list of dicts."""
        return [m.to_dict() for m in self._transcript.messages]

    def reset(self) -> None:
        """Clear transcript and counters for a fresh session."""
        self._transcript.clear()
        self._transcript.add("system", self._system_prompt)
        self._turn_count = 0
        self._error_count = 0
        self._last_error = None

    @staticmethod
    def _extract_content(response: dict[str, Any]) -> str:
        """Extract text content from an OpenAI-compatible response."""
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return message.get("content", "")
