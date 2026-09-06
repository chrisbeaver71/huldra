"""Huldra V1 Recovery/Status Visibility.

Provides:
- Backend health status reporting
- Session status (turn count, error count, last error)
- Tool call failure tracking
- Restart/reclaim status
- Clean shutdown coordination
- Status summary for display
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ComponentStatus(Enum):
    """Status of a system component."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class ComponentReport:
    """Status report for a single component."""
    name: str
    status: ComponentStatus
    detail: str = ""
    latency_ms: float = 0.0
    last_checked: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "latency_ms": round(self.latency_ms, 1),
            "last_checked": self.last_checked,
        }


@dataclass
class ToolCallRecord:
    """Record of a tool call for failure tracking."""
    tool_name: str
    success: bool
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0


class StatusTracker:
    """Tracks status of all V1 components.

    Provides a unified view of:
    - Backend health
    - Session state
    - Tool call success/failure rates
    - Error history
    - Shutdown state
    """

    def __init__(self, status_dir: Optional[Path] = None):
        self._status_dir = status_dir or Path("E:/Huldra/.hermes-live")
        self._status_dir.mkdir(parents=True, exist_ok=True)
        self._components: dict[str, ComponentReport] = {}
        self._tool_calls: list[ToolCallRecord] = []
        self._session_turns: int = 0
        self._session_errors: int = 0
        self._last_error: Optional[str] = None
        self._shutdown_requested: bool = False
        self._shutdown_complete: bool = False
        self._start_time: float = time.time()

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def update_component(
        self,
        name: str,
        status: ComponentStatus,
        detail: str = "",
        latency_ms: float = 0.0,
    ) -> None:
        """Update the status of a component."""
        self._components[name] = ComponentReport(
            name=name,
            status=status,
            detail=detail,
            latency_ms=latency_ms,
        )

    def get_component(self, name: str) -> Optional[ComponentReport]:
        return self._components.get(name)

    def record_tool_call(self, record: ToolCallRecord) -> None:
        """Record a tool call result."""
        self._tool_calls.append(record)
        # Keep only last 100 records
        if len(self._tool_calls) > 100:
            self._tool_calls = self._tool_calls[-100:]

    def record_turn(self, success: bool, error: Optional[str] = None) -> None:
        """Record a conversation turn result."""
        self._session_turns += 1
        if not success:
            self._session_errors += 1
            self._last_error = error

    def request_shutdown(self) -> None:
        """Request clean shutdown."""
        self._shutdown_requested = True
        logger.info("Shutdown requested")

    def complete_shutdown(self) -> None:
        """Mark shutdown as complete."""
        self._shutdown_complete = True
        self._persist_status()
        logger.info("Shutdown complete")

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_requested and not self._shutdown_complete

    def get_tool_stats(self) -> dict[str, Any]:
        """Get tool call statistics."""
        if not self._tool_calls:
            return {"total": 0, "success": 0, "failure": 0, "success_rate": 0.0}

        total = len(self._tool_calls)
        success = sum(1 for tc in self._tool_calls if tc.success)
        return {
            "total": total,
            "success": success,
            "failure": total - success,
            "success_rate": round(success / total, 3) if total > 0 else 0.0,
        }

    def get_summary(self) -> dict[str, Any]:
        """Get a full status summary."""
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "components": {
                name: comp.to_dict()
                for name, comp in self._components.items()
            },
            "session": {
                "turns": self._session_turns,
                "errors": self._session_errors,
                "last_error": self._last_error,
            },
            "tools": self.get_tool_stats(),
            "shutdown": {
                "requested": self._shutdown_requested,
                "complete": self._shutdown_complete,
            },
        }

    def _persist_status(self) -> None:
        """Write status to disk for recovery visibility."""
        status_file = self._status_dir / "v1_status.json"
        try:
            status_file.write_text(
                json.dumps(self.get_summary(), indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Failed to persist status: %s", e)

    def save_snapshot(self) -> Path:
        """Save a status snapshot and return the path."""
        self._persist_status()
        return self._status_dir / "v1_status.json"

    def check_backend_health(
        self,
        name: str,
        check_fn,
        force: bool = False,
    ) -> ComponentReport:
        """Check backend health and update component status.

        check_fn should return a BackendHealth or similar object.
        """
        try:
            health = check_fn(force=force)
            status_map = {
                "healthy": ComponentStatus.HEALTHY,
                "degraded": ComponentStatus.DEGRADED,
                "unreachable": ComponentStatus.UNREACHABLE,
            }
            status = status_map.get(
                getattr(health, "status", "unknown"),
                ComponentStatus.UNKNOWN,
            )
            report = ComponentReport(
                name=name,
                status=status,
                detail=getattr(health, "error", "") or "",
                latency_ms=getattr(health, "latency_ms", 0.0),
            )
            self._components[name] = report
            return report
        except Exception as e:
            report = ComponentReport(
                name=name,
                status=ComponentStatus.UNREACHABLE,
                detail=str(e),
            )
            self._components[name] = report
            return report
