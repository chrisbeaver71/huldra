"""Optional Huldra worker/sub-agent engine.

The primary assistant owns user-facing conversation.  This module provides a
small, explicit routing boundary for narrow delegated work.  It only routes to
profiles marked ``role="worker"`` and ``optional=true``; it never changes the
primary profile selection or silently falls back to a worker for conversation.

The engine is deterministic and model-agnostic.  It verifies staged assets,
checks declared hardware requirements, builds a llama.cpp launch command, and
constructs a bounded OpenAI-compatible request payload.  It does not benchmark
or auto-download model assets.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from huldra_hardware import HardwareProfile
from huldra_profiles import Profile, ProfileCatalog
from huldra_recommender import FitLevel, check_requirements


ELIGIBLE_WORKER_TASKS = frozenset(
    {
        "extraction",
        "classification",
        "context_pruning",
        "repo_inspection",
        "file_inspection",
        "normalization",
        "json_conversion",
        "bounded_scripting",
    }
)


def normalize_task_kind(task_kind: str) -> str:
    """Normalize the small, closed worker-task vocabulary."""
    return (task_kind or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_worker_task_eligible(task_kind: str) -> bool:
    return normalize_task_kind(task_kind) in ELIGIBLE_WORKER_TASKS


@dataclass
class WorkerRoute:
    """A routing decision made before a worker is invoked."""

    task_kind: str
    eligible: bool
    available: bool
    profile_id: Optional[str] = None
    reason: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def routed_to_worker(self) -> bool:
        return self.eligible and self.available and self.profile_id is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind,
            "eligible": self.eligible,
            "available": self.available,
            "profile_id": self.profile_id,
            "reason": self.reason,
            "checks": self.checks,
            "routed_to_worker": self.routed_to_worker,
        }


class WorkerEngineError(RuntimeError):
    """Raised when a worker route or launch cannot be constructed."""


class WorkerEngine:
    """Optional delegated-worker engine backed by a profile catalog.

    ``huldra_home`` is the root containing ``models/`` and ``runtimes/``.
    Asset verification is fail-closed.  ``auto_download`` is deliberately not
    implemented here: a missing worker asset returns an unavailable route so
    the primary assistant can handle the task itself.
    """

    def __init__(
        self,
        catalog: ProfileCatalog,
        huldra_home: Path | str,
        hardware: Optional[HardwareProfile] = None,
        worker_profile_id: str = "ling30-tiny-worker",
    ) -> None:
        self.catalog = catalog
        self.huldra_home = Path(huldra_home).expanduser()
        self.hardware = hardware
        self.worker_profile_id = worker_profile_id

    @property
    def profile(self) -> Optional[Profile]:
        return self.catalog.get(self.worker_profile_id)

    def resolve_artifact(self, path: str) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.huldra_home / candidate

    @staticmethod
    def _sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

    def verify_assets(self, hash_artifacts: bool = True) -> tuple[bool, list[str]]:
        """Verify model, runtime, and template artifacts against the profile.

        Returns ``(ok, errors)``.  Hashing the 6.956 GB model is intentional
        when ``hash_artifacts`` is true and should be performed at staging or
        startup, not for every individual task route.
        """
        profile = self.profile
        if profile is None:
            return False, [f"worker profile not found: {self.worker_profile_id}"]
        if profile.role != "worker" or not profile.optional:
            return False, ["selected profile is not an optional worker profile"]

        errors: list[str] = []
        for label, artifact in (
            ("model", profile.model_artifact),
            ("runtime", profile.runtime_artifact),
            ("template", profile.template_artifact),
        ):
            if artifact is None:
                errors.append(f"{label} artifact is not declared")
                continue
            path = self.resolve_artifact(artifact.path)
            if not path.is_file():
                errors.append(f"{label} artifact missing: {path}")
                continue
            if artifact.size_bytes and path.stat().st_size != artifact.size_bytes:
                errors.append(
                    f"{label} size mismatch: {path.stat().st_size} != "
                    f"{artifact.size_bytes}"
                )
            if hash_artifacts and artifact.sha256:
                actual = self._sha256(path)
                if actual.lower() != artifact.sha256.lower():
                    errors.append(
                        f"{label} sha256 mismatch: {actual} != {artifact.sha256}"
                    )
        return not errors, errors

    def route(
        self,
        task_kind: str,
        *,
        verify_hash: bool = False,
    ) -> WorkerRoute:
        """Return a fail-closed route; non-eligible work stays on the primary."""
        normalized = normalize_task_kind(task_kind)
        if normalized not in ELIGIBLE_WORKER_TASKS:
            return WorkerRoute(
                task_kind=normalized,
                eligible=False,
                available=False,
                reason="task kind is outside the bounded worker allowlist",
            )

        profile = self.profile
        if profile is None:
            return WorkerRoute(
                task_kind=normalized,
                eligible=True,
                available=False,
                reason=f"worker profile not found: {self.worker_profile_id}",
            )
        if profile.role != "worker" or not profile.optional:
            return WorkerRoute(
                task_kind=normalized,
                eligible=True,
                available=False,
                reason="selected profile is not an optional worker profile",
            )

        assets_ok, asset_errors = self.verify_assets(hash_artifacts=verify_hash)
        if not assets_ok:
            return WorkerRoute(
                task_kind=normalized,
                eligible=True,
                available=False,
                profile_id=profile.id,
                reason="; ".join(asset_errors),
            )

        checks: list[dict[str, Any]] = []
        if self.hardware is not None:
            fit, requirement_checks, reasons = check_requirements(self.hardware, profile)
            checks = [item.to_dict() for item in requirement_checks]
            if fit == FitLevel.INSUFFICIENT:
                return WorkerRoute(
                    task_kind=normalized,
                    eligible=True,
                    available=False,
                    profile_id=profile.id,
                    reason="; ".join(reasons) or "declared hardware requirements are insufficient",
                    checks=checks,
                )

        return WorkerRoute(
            task_kind=normalized,
            eligible=True,
            available=True,
            profile_id=profile.id,
            reason="worker assets and declared requirements are available",
            checks=checks,
        )

    def build_server_command(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> list[str]:
        """Build a llama.cpp command without starting a process."""
        profile = self.profile
        if profile is None or profile.model_artifact is None:
            raise WorkerEngineError("worker model profile/artifact is unavailable")
        if profile.runtime.backend_type != "llama.cpp":
            raise WorkerEngineError(
                f"unsupported worker backend: {profile.runtime.backend_type}"
            )

        binary = self.resolve_artifact(profile.runtime.backend_binary)
        model = self.resolve_artifact(profile.model_artifact.path)
        if not binary.is_file():
            raise WorkerEngineError(f"worker runtime missing: {binary}")
        if not model.is_file():
            raise WorkerEngineError(f"worker model missing: {model}")

        command = [str(binary), "--model", str(model)]
        args = list(profile.runtime.backend_args)
        if host is not None and "--host" in args:
            args[args.index("--host") + 1] = host
        if port is not None and "--port" in args:
            args[args.index("--port") + 1] = str(port)
        command.extend(args)
        return command

    def build_chat_payload(
        self,
        task_kind: str,
        instruction: str,
        *,
        max_tokens: int = 512,
        enable_thinking: bool = False,
    ) -> dict[str, Any]:
        """Build a bounded worker request for an OpenAI-compatible server."""
        normalized = normalize_task_kind(task_kind)
        if normalized not in ELIGIBLE_WORKER_TASKS:
            raise WorkerEngineError(
                f"task kind '{normalized}' is not eligible for worker delegation"
            )
        profile = self.profile
        if profile is None:
            raise WorkerEngineError("worker profile is unavailable")
        return {
            "model": profile.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Huldra's bounded worker. Perform only the requested "
                        "task, return concise machine-usable output, and do not act as "
                        "the user's main assistant."
                    ),
                },
                {"role": "user", "content": instruction},
            ],
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 20,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        }

    def launch(self, *, host: Optional[str] = None, port: Optional[int] = None) -> subprocess.Popen:
        """Start the worker server after verifying staged files exist.

        This method does not download, benchmark, or expose a public bind.  The
        profile defaults to loopback and callers should terminate the returned
        process after the bounded task completes.
        """
        command = self.build_server_command(host=host, port=port)
        return subprocess.Popen(
            command,
            cwd=str(self.huldra_home),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def default_worker_engine(
    huldra_home: Path | str,
    hardware: Optional[HardwareProfile] = None,
) -> WorkerEngine:
    """Construct the default optional worker engine from the V1 catalog."""
    from huldra_profiles import create_v1_default_catalog

    return WorkerEngine(
        catalog=create_v1_default_catalog(),
        huldra_home=huldra_home,
        hardware=hardware,
    )


__all__ = [
    "ELIGIBLE_WORKER_TASKS",
    "WorkerEngine",
    "WorkerEngineError",
    "WorkerRoute",
    "default_worker_engine",
    "is_worker_task_eligible",
    "normalize_task_kind",
]
