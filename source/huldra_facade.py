"""Huldra V1 Product Adapter/Facade.

Thin orchestration layer over upstream Hermes.  Provides a single entry
point for the full Huldra product path:

    first-run detect → recommend → asset/config resolve → launch → session → status

This module does NOT rewrite or extend any upstream Hermes machinery.
It imports upstream primitives (BackendConfig, LocalModelBackend) and
wires them to Huldra-owned modules (profiles, hardware, recommender,
state, status, chat, tools, file context).

Usage::

    from huldra_facade import HuldraFacade

    facade = HuldraFacade()
    result = facade.first_run()          # detect + recommend
    session = facade.launch_session()    # resolve assets + start session
    status = facade.get_status()         # component health
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend import BackendConfig, LocalModelBackend
from huldra_chat import ChatSession
from huldra_file_context import PathGuard
from huldra_hardware import HardwareProfile, detect_hardware, save_hardware_profile, load_hardware_profile
from huldra_profiles import Profile, ProfileCatalog, ProfileCatalogError, create_v1_default_catalog
from huldra_recommender import (
    FitLevel,
    ProfileRecommendation,
    format_recommendation_report,
    get_best_profile,
    recommend_profiles,
)
from huldra_state import MemoryStore, StateStore
from huldra_status import ComponentStatus, StatusTracker
from huldra_tools import ToolRegistry, register_v1_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Huldra-owned paths (external to the code tree)
# ---------------------------------------------------------------------------

def _resolve_huldra_home() -> Path:
    """Resolve HULDRA_HOME from env or default."""
    configured = os.environ.get("HULDRA_HOME")
    if configured:
        return Path(configured)
    # Walk up from this file to find a directory containing ops/hermes
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "ops" / "hermes").is_dir():
            return parent
    return Path.cwd()


def _resolve_config_dir(huldra_home: Path) -> Path:
    """Resolve Huldra config directory."""
    return huldra_home / "config"


def _resolve_models_dir(huldra_home: Path) -> Path:
    """Resolve Huldra models directory."""
    return huldra_home / "Models"


def _resolve_state_dir(huldra_home: Path) -> Path:
    """Resolve Huldra state directory (outside code tree)."""
    return huldra_home / "state"


def _resolve_evidence_dir(huldra_home: Path) -> Path:
    """Resolve Huldra evidence directory."""
    return huldra_home / "evidence"


def _resolve_status_dir(huldra_home: Path) -> Path:
    """Resolve Huldra live status directory."""
    return huldra_home / ".hermes-live"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class FirstRunResult:
    """Result of first-run detection and recommendation."""
    hardware: HardwareProfile
    recommendations: list[ProfileRecommendation]
    best_profile: Optional[ProfileRecommendation] = None
    hardware_cached: bool = False
    report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hardware": self.hardware.to_dict(),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "best_profile": self.best_profile.to_dict() if self.best_profile else None,
            "hardware_cached": self.hardware_cached,
        }


class AssetVerificationError(Exception):
    """Raised when asset verification fails (missing or hash mismatch)."""
    pass


@dataclass
class AssetStatus:
    """Status of a single asset (model, runtime, template)."""
    name: str
    path: str
    exists: bool = False
    size_bytes: int = 0
    sha256: str = ""
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "verified": self.verified,
        }


@dataclass
class LaunchResult:
    """Result of launching a session."""
    profile_id: str
    profile_name: str
    backend_name: str
    backend_url: str
    session_active: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "backend_name": self.backend_name,
            "backend_url": self.backend_url,
            "session_active": self.session_active,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

class HuldraFacade:
    """Thin adapter/facade over upstream Hermes for Huldra V1.

    Orchestrates: profile catalog, hardware detection, asset verification,
    backend/config resolution, selector/manual override, session management,
    and status reporting.

    All Huldra-owned state lives outside the code tree under HULDRA_HOME.
    """

    def __init__(
        self,
        huldra_home: Optional[Path] = None,
        catalog_path: Optional[Path] = None,
    ):
        self._huldra_home = huldra_home or _resolve_huldra_home()
        self._config_dir = _resolve_config_dir(self._huldra_home)
        self._models_dir = _resolve_models_dir(self._huldra_home)
        self._state_dir = _resolve_state_dir(self._huldra_home)
        self._evidence_dir = _resolve_evidence_dir(self._huldra_home)
        self._status_dir = _resolve_status_dir(self._huldra_home)

        # Ensure external dirs exist
        for d in (self._state_dir, self._evidence_dir, self._status_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Initialize subsystems
        self._state = StateStore(state_dir=self._state_dir)
        self._memory = MemoryStore(state_dir=self._state_dir)
        self._status = StatusTracker(status_dir=self._status_dir)
        self._path_guard = PathGuard(
            huldra_root=str(self._huldra_home),
            allowed_roots=[
                str(self._huldra_home),
                str(self._huldra_home / "Results"),
                str(self._huldra_home / "docs"),
                str(self._huldra_home / "evidence"),
                str(self._huldra_home / "boards" / "huldra"),
                str(self._huldra_home / "Models"),
            ],
        )
        self._tool_registry = ToolRegistry()
        register_v1_tools(self._tool_registry)

        # Load or create catalog
        self._catalog_path = catalog_path or (
            self._config_dir / "profile_catalog.json"
        )
        self._catalog: Optional[ProfileCatalog] = None
        self._hardware: Optional[HardwareProfile] = None
        self._session: Optional[ChatSession] = None

    # -- Properties --

    @property
    def huldra_home(self) -> Path:
        return self._huldra_home

    @property
    def catalog(self) -> ProfileCatalog:
        if self._catalog is None:
            self._catalog = self._load_or_create_catalog()
        return self._catalog

    @property
    def hardware(self) -> Optional[HardwareProfile]:
        return self._hardware

    @property
    def session(self) -> Optional[ChatSession]:
        return self._session

    @property
    def status(self) -> StatusTracker:
        return self._status

    @property
    def state(self) -> StateStore:
        return self._state

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    # -- Catalog management --

    def _load_or_create_catalog(self) -> ProfileCatalog:
        """Load catalog from disk or create the V1 default."""
        if self._catalog_path.exists():
            try:
                return ProfileCatalog.from_file(self._catalog_path)
            except ProfileCatalogError as e:
                logger.warning("Failed to load catalog from %s: %s", self._catalog_path, e)
        catalog = create_v1_default_catalog()
        # Persist for next time
        try:
            catalog.save(self._catalog_path)
        except OSError as e:
            logger.warning("Failed to persist catalog: %s", e)
        return catalog

    def save_catalog(self) -> None:
        """Persist the current catalog to disk."""
        self.catalog.save(self._catalog_path)

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        """Get a profile by ID from the catalog."""
        return self.catalog.get(profile_id)

    def list_profiles(self) -> list[Profile]:
        """List all profiles in the catalog."""
        return list(self.catalog.profiles)

    def list_primary_profiles(self) -> list[Profile]:
        """List only primary (user-facing, non-optional) profiles."""
        return [
            p for p in self.catalog.profiles
            if p.role == "user-facing" and not p.optional
        ]

    # -- First-run detection --

    def detect_hardware(self, use_cache: bool = True) -> HardwareProfile:
        """Run hardware detection, optionally using cached results.

        Cache lives at $HULDRA_HOME/state/hardware_profile.json.
        """
        cache_path = self._state_dir / "hardware_profile.json"
        if use_cache and cache_path.exists():
            cached = load_hardware_profile(cache_path)
            if cached is not None:
                self._hardware = cached
                self._status.update_component(
                    "hardware",
                    ComponentStatus.HEALTHY,
                    detail="loaded from cache",
                )
                return cached

        hw = detect_hardware(huldra_home=str(self._huldra_home))
        self._hardware = hw
        save_hardware_profile(hw, cache_path)
        self._status.update_component(
            "hardware",
            ComponentStatus.HEALTHY,
            detail=f"detected: GPU={hw.gpu.name}, RAM={hw.ram_total_gb:.1f}GB",
        )
        return hw

    def recommend(
        self,
        manual_override: Optional[str] = None,
    ) -> list[ProfileRecommendation]:
        """Recommend profiles based on detected hardware.

        If no hardware has been detected yet, runs detection first.
        """
        if self._hardware is None:
            self.detect_hardware()
        assert self._hardware is not None
        return recommend_profiles(self._hardware, self.catalog, manual_override)

    def first_run(
        self,
        manual_override: Optional[str] = None,
        use_hw_cache: bool = True,
    ) -> FirstRunResult:
        """Execute the full first-run path: detect → recommend.

        Returns a FirstRunResult with hardware info, recommendations,
        and a human-readable report.
        """
        hw = self.detect_hardware(use_cache=use_hw_cache)
        recs = self.recommend(manual_override)
        best = get_best_profile(hw, self.catalog, manual_override)
        report = format_recommendation_report(hw, recs)

        # Persist the selection
        if best:
            self._state.set("session.active_profile", best.profile.id)

        self._status.update_component(
            "recommender",
            ComponentStatus.HEALTHY,
            detail=f"best={best.profile.id if best else 'none'}",
        )

        return FirstRunResult(
            hardware=hw,
            recommendations=recs,
            best_profile=best,
            hardware_cached=use_hw_cache and (self._state_dir / "hardware_profile.json").exists(),
            report=report,
        )

    # -- Asset verification --

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        """Compute SHA-256 hex digest of a file, reading in 1MB chunks."""
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)  # 1MB
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def verify_assets(
        self,
        profile_id: Optional[str] = None,
        check_sha256: bool = False,
    ) -> list[AssetStatus]:
        """Verify that all artifacts for a profile exist on disk.

        If profile_id is None, verifies the active profile.
        If check_sha256 is True, computes and verifies SHA-256 hashes
        for artifacts that declare one.  Fails closed: an artifact with
        a declared hash that doesn't match is marked as NOT verified.

        Returns a list of AssetStatus for each declared artifact.
        """
        if profile_id is None:
            profile_id = self._state.get("session.active_profile")
        if profile_id is None:
            return []

        profile = self.catalog.get(profile_id)
        if profile is None:
            return []

        results: list[AssetStatus] = []
        all_artifacts = [profile.model_artifact, profile.runtime_artifact, profile.template_artifact]
        all_artifacts.extend(profile.auxiliary_artifacts)
        for artifact_ref in all_artifacts:
            if artifact_ref is None:
                continue
            # Resolve path relative to HULDRA_HOME
            artifact_path = self._huldra_home / artifact_ref.path
            exists = artifact_path.exists()
            size = artifact_path.stat().st_size if exists else 0

            # Determine verification status
            verified = False
            if exists:
                if artifact_ref.sha256 and check_sha256:
                    # Compute and compare SHA-256
                    actual_hash = self._compute_sha256(artifact_path)
                    verified = actual_hash.lower() == artifact_ref.sha256.lower()
                    if not verified:
                        logger.error(
                            "SHA-256 mismatch for %s: expected %s, got %s",
                            artifact_ref.name, artifact_ref.sha256, actual_hash,
                        )
                elif artifact_ref.size_bytes and size != artifact_ref.size_bytes:
                    # Size mismatch without hash check
                    logger.warning(
                        "Size mismatch for %s: expected %d, got %d",
                        artifact_ref.name, artifact_ref.size_bytes, size,
                    )
                    verified = False
                else:
                    # Exists and no hash to check (or size matches)
                    verified = True

            results.append(AssetStatus(
                name=artifact_ref.name,
                path=str(artifact_path),
                exists=exists,
                size_bytes=size,
                sha256=artifact_ref.sha256,
                verified=verified,
            ))
            status = ComponentStatus.HEALTHY if (exists and verified) else ComponentStatus.UNREACHABLE
            detail_parts = ["found" if exists else "missing"]
            if exists and not verified:
                detail_parts.append("HASH_MISMATCH" if (artifact_ref.sha256 and check_sha256) else "SIZE_MISMATCH")
            self._status.update_component(
                f"asset:{artifact_ref.name}",
                status,
                detail=f"{': '.join(detail_parts)}: {artifact_path}",
            )
        return results

    def assert_assets_valid(
        self,
        profile_id: Optional[str] = None,
    ) -> None:
        """Fail closed: raise if any declared artifact is missing or hash-mismatched.

        This is the strict verification path for launch.  Unlike
        verify_assets() which returns a list for inspection, this
        method raises AssetVerificationError on the first failure.
        """
        assets = self.verify_assets(profile_id, check_sha256=True)
        failures = [a for a in assets if not a.verified]
        if failures:
            msgs = []
            for a in failures:
                if not a.exists:
                    msgs.append(f"{a.name}: missing at {a.path}")
                else:
                    msgs.append(f"{a.name}: SHA-256 mismatch at {a.path}")
            raise AssetVerificationError(
                f"Asset verification failed for {len(failures)} artifact(s): "
                + "; ".join(msgs)
            )

    # -- Backend/config resolution --

    def resolve_backend(self, profile_id: Optional[str] = None) -> Optional[BackendConfig]:
        """Resolve a BackendConfig for the given (or active) profile.

        The backend URL defaults to 127.0.0.1:<port> based on the
        profile's runtime config. No external services are contacted.
        """
        if profile_id is None:
            profile_id = self._state.get("session.active_profile")
        if profile_id is None:
            return None

        profile = self.catalog.get(profile_id)
        if profile is None:
            return None

        # Extract host/port from backend_args
        host = "127.0.0.1"
        port = "8080"
        args = profile.runtime.backend_args
        for i, arg in enumerate(args):
            if arg == "--host" and i + 1 < len(args):
                host = args[i + 1]
            if arg == "--port" and i + 1 < len(args):
                port = args[i + 1]

        base_url = f"http://{host}:{port}"
        return BackendConfig(
            name=profile.id,
            base_url=base_url,
            default_model=profile.model_name,
            timeout_seconds=30.0,
        )

    # -- Launch --

    def launch_session(
        self,
        profile_id: Optional[str] = None,
        system_prompt: str = "You are Huldra, a local AI assistant.",
    ) -> LaunchResult:
        """Launch a chat session for the given (or active) profile.

        Resolves backend config, creates a LocalModelBackend, and
        wraps it in a ChatSession. Does NOT actually start the model
        server — that is the user's responsibility (ik_llama-server,
        llama-server, etc.).
        """
        if profile_id is None:
            profile_id = self._state.get("session.active_profile")
        if profile_id is None:
            return LaunchResult(
                profile_id="",
                profile_name="",
                backend_name="",
                backend_url="",
                error="No active profile. Run first_run() first.",
            )

        profile = self.catalog.get(profile_id)
        if profile is None:
            return LaunchResult(
                profile_id=profile_id,
                profile_name="",
                backend_name="",
                backend_url="",
                error=f"Profile '{profile_id}' not found in catalog.",
            )

        backend_config = self.resolve_backend(profile_id)
        if backend_config is None:
            return LaunchResult(
                profile_id=profile_id,
                profile_name=profile.name,
                backend_name="",
                backend_url="",
                error="Could not resolve backend config.",
            )

        backend = LocalModelBackend(backend_config)
        transcript_path = self._state_dir / f"transcript_{profile_id}.json"
        self._session = ChatSession(
            backend=backend,
            system_prompt=system_prompt,
            transcript_path=transcript_path,
        )

        self._state.set("session.active_profile", profile_id)
        self._state.set("session.active_backend_url", backend_config.base_url)
        self._status.update_component(
            "backend",
            ComponentStatus.UNKNOWN,
            detail=f"profile={profile_id}, url={backend_config.base_url}",
        )

        return LaunchResult(
            profile_id=profile_id,
            profile_name=profile.name,
            backend_name=profile.runtime.backend_type,
            backend_url=backend_config.base_url,
            session_active=True,
        )

    # -- Manual override selector --

    def select_profile(self, profile_id: str) -> ProfileRecommendation:
        """Manually select a profile (override recommendation).

        Validates the profile exists and returns its fit assessment.
        Persists the selection as the active profile.
        """
        profile = self.catalog.get(profile_id)
        if profile is None:
            raise ValueError(f"Profile '{profile_id}' not found in catalog")

        if self._hardware is None:
            self.detect_hardware()
        assert self._hardware is not None

        recs = recommend_profiles(self._hardware, self.catalog, manual_override=profile_id)
        # Find the override recommendation
        for rec in recs:
            if rec.profile.id == profile_id:
                self._state.set("session.active_profile", profile_id)
                return rec

        # Should not happen, but defensive
        from huldra_recommender import check_requirements
        fit, checks, reasons = check_requirements(self._hardware, profile)
        reasons.append(f"MANUAL OVERRIDE requested for '{profile_id}'")
        rec = ProfileRecommendation(
            profile=profile,
            fit=fit,
            checks=checks,
            reasons=reasons,
            manual_override_allowed=True,
        )
        self._state.set("session.active_profile", profile_id)
        return rec

    # -- Status --

    def get_status(self) -> dict[str, Any]:
        """Get full status summary including Huldra subsystems."""
        summary = self._status.get_summary()
        summary["huldra"] = {
            "huldra_home": str(self._huldra_home),
            "active_profile": self._state.get("session.active_profile"),
            "catalog_version": self.catalog.version,
            "catalog_profiles": len(self.catalog.profiles),
            "hardware_detected": self._hardware is not None,
            "session_active": self._session is not None,
        }
        return summary

    def health_check(self) -> dict[str, Any]:
        """Check health of all components."""
        result = {
            "catalog": "healthy" if self.catalog else "not_loaded",
            "hardware": "detected" if self._hardware else "not_detected",
            "session": "active" if self._session else "inactive",
        }
        # Check active profile assets
        active_id = self._state.get("session.active_profile")
        if active_id:
            assets = self.verify_assets(active_id)
            result["assets"] = {
                a.name: "present" if a.exists else "missing"
                for a in assets
            }
        return result

    # -- Tool access --

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get all registered tool schemas in OpenAI format."""
        return self._tool_registry.get_schemas()

    def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Validate and execute a tool call."""
        return self._tool_registry.execute_tool(name, args)

    # -- State access --

    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference in durable state."""
        self._state.set(f"preferences.{key}", value)

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference from durable state."""
        return self._state.get(f"preferences.{key}", default)

    def remember(self, key: str, content: str, tags: Optional[list[str]] = None) -> None:
        """Store a memory entry."""
        self._memory.remember(key, content, tags)

    def recall(self, key: str) -> Optional[str]:
        """Recall a memory entry."""
        return self._memory.recall(key)

    # -- Shutdown --

    def shutdown(self) -> None:
        """Clean shutdown of all Huldra subsystems."""
        self._status.request_shutdown()
        if self._session:
            # Persist transcript if session has one
            pass
        self._status.complete_shutdown()
        logger.info("Huldra facade shutdown complete")
