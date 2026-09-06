"""Local model backend abstraction for Huldra V1.

Provides a unified interface to local OpenAI-compatible endpoints
(llama-server, Ollama, vLLM, etc.) with:
- Health checking and endpoint discovery
- Secret-free configuration (API keys optional for local servers)
- Graceful degradation on backend loss
- Structured error types for downstream handling
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BackendStatus(Enum):
    """Health status of a model backend."""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


@dataclass
class BackendConfig:
    """Configuration for a single model backend endpoint."""
    name: str
    base_url: str
    default_model: str
    api_key_env: Optional[str] = None  # env var name; None = no auth needed
    api_key: Optional[str] = None      # direct key; takes precedence over env
    timeout_seconds: float = 30.0
    models: list[str] = field(default_factory=list)
    health_check_interval: float = 60.0

    def get_api_key(self) -> Optional[str]:
        """Resolve API key: direct value > env var > None."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            import os
            return os.environ.get(self.api_key_env)
        return None

    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/models"

    def health_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/health"


@dataclass
class BackendHealth:
    """Result of a health check."""
    status: BackendStatus
    latency_ms: float = 0.0
    error: Optional[str] = None
    models_available: list[str] = field(default_factory=list)
    checked_at: float = 0.0

    def __post_init__(self):
        if self.checked_at == 0.0:
            self.checked_at = time.time()


class BackendError(Exception):
    """Base error for backend operations."""
    def __init__(self, backend_name: str, message: str, recoverable: bool = True):
        self.backend_name = backend_name
        self.recoverable = recoverable
        super().__init__(f"[{backend_name}] {message}")


class BackendUnreachableError(BackendError):
    """Backend is not reachable."""
    def __init__(self, backend_name: str, detail: str = ""):
        super().__init__(
            backend_name,
            f"Backend unreachable{f': {detail}' if detail else ''}",
            recoverable=True,
        )


class BackendModelNotFoundError(BackendError):
    """Requested model is not available on this backend."""
    def __init__(self, backend_name: str, model: str, available: list[str]):
        avail_str = ", ".join(available[:5]) if available else "(none)"
        super().__init__(
            backend_name,
            f"Model '{model}' not found. Available: {avail_str}",
            recoverable=False,
        )


class LocalModelBackend:
    """Manages connection to a local OpenAI-compatible model endpoint.

    Usage:
        config = BackendConfig(
            name="ollama",
            base_url="http://127.0.0.1:11434/v1",
            default_model="hermes3:8b",
        )
        backend = LocalModelBackend(config)
        health = backend.check_health()
        if health.status == BackendStatus.HEALTHY:
            response = backend.chat_completion(messages, model="hermes3:8b")
    """

    def __init__(self, config: BackendConfig):
        self.config = config
        self._last_health: Optional[BackendHealth] = None
        self._last_health_check: float = 0.0

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_healthy(self) -> bool:
        if self._last_health is None:
            return False
        return self._last_health.status in (BackendStatus.HEALTHY, BackendStatus.DEGRADED)

    def check_health(self, force: bool = False) -> BackendHealth:
        """Check backend health. Caches result for health_check_interval seconds."""
        now = time.time()
        if (
            not force
            and self._last_health is not None
            and (now - self._last_health_check) < self.config.health_check_interval
        ):
            return self._last_health

        start = time.monotonic()
        try:
            req = urllib.request.Request(
                self.config.health_url(),
                headers={"Accept": "application/json"},
            )
            api_key = self.config.get_api_key()
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")

            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                latency = (time.monotonic() - start) * 1000
                data = json.loads(resp.read().decode("utf-8"))
                self._last_health = BackendHealth(
                    status=BackendStatus.HEALTHY,
                    latency_ms=latency,
                    checked_at=now,
                )
                self._last_health_check = now
                logger.info("Backend %s healthy (%.0fms)", self.name, latency)
                return self._last_health

        except urllib.error.URLError as e:
            latency = (time.monotonic() - start) * 1000
            self._last_health = BackendHealth(
                status=BackendStatus.UNREACHABLE,
                latency_ms=latency,
                error=str(e),
                checked_at=now,
            )
            self._last_health_check = now
            logger.warning("Backend %s unreachable: %s", self.name, e)
            return self._last_health

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            self._last_health = BackendHealth(
                status=BackendStatus.DEGRADED,
                latency_ms=latency,
                error=str(e),
                checked_at=now,
            )
            self._last_health_check = now
            logger.warning("Backend %s degraded: %s", self.name, e)
            return self._last_health

    def list_models(self) -> list[str]:
        """List available models from the backend."""
        try:
            req = urllib.request.Request(
                self.config.models_url(),
                headers={"Accept": "application/json"},
            )
            api_key = self.config.get_api_key()
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")

            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("id", "") for m in data.get("data", [])]
                return [m for m in models if m]
        except Exception as e:
            logger.warning("Failed to list models from %s: %s", self.name, e)
            return []

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Returns the parsed JSON response from the OpenAI-compatible endpoint.
        Raises BackendUnreachableError if the endpoint is down.
        Raises BackendError on other failures.
        """
        model = model or self.config.default_model

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.config.chat_completions_url(),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        api_key = self.config.get_api_key()
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise BackendUnreachableError(self.name, str(e)) from e
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise BackendError(
                self.name,
                f"HTTP {e.code}: {error_body[:200]}",
                recoverable=e.code >= 500,
            ) from e
        except Exception as e:
            raise BackendError(self.name, str(e)) from e

    def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        """Stream a chat completion, yielding content deltas."""
        model = model or self.config.default_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.config.chat_completions_url(),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        api_key = self.config.get_api_key()
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                for line in resp:
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except urllib.error.URLError as e:
            raise BackendUnreachableError(self.name, str(e)) from e
        except Exception as e:
            raise BackendError(self.name, str(e)) from e


def load_backend_from_config(config_path: str) -> list[LocalModelBackend]:
    """Load backend configurations from a YAML/JSON config file.

    The config file should have a 'providers' dict mapping names to
    BackendConfig-compatible dicts, or a top-level 'backend' key for
    single-backend configs.
    """
    import os
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    content = path.read_text(encoding="utf-8")

    # Try YAML first, fall back to JSON
    try:
        import yaml
        data = yaml.safe_load(content)
    except ImportError:
        data = json.loads(content)

    backends = []

    # Single backend config
    if "backend" in data:
        bcfg = data["backend"]
        backends.append(LocalModelBackend(BackendConfig(
            name=bcfg.get("name", "default"),
            base_url=bcfg["base_url"],
            default_model=bcfg.get("default_model", ""),
            api_key_env=bcfg.get("key_env"),
            timeout_seconds=bcfg.get("timeout_seconds", 30.0),
            models=bcfg.get("models", []),
        )))
        return backends

    # Multiple providers
    providers = data.get("providers", {})
    for name, pcfg in providers.items():
        backends.append(LocalModelBackend(BackendConfig(
            name=name,
            base_url=pcfg.get("base_url", pcfg.get("api", "")),
            default_model=pcfg.get("default_model", ""),
            api_key_env=pcfg.get("key_env"),
            timeout_seconds=pcfg.get("timeout_seconds", 30.0),
            models=pcfg.get("models", []),
        )))

    return backends
