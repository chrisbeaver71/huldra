"""Huldra V1 Profile Catalog and Schema.

Versioned, declarative profile catalog for local model deployment.

Each profile owns:
- Artifact paths (GGUF model, runtime binary, template)
- Source/revision/hash/license fields
- Runtime/backend type (ik_llama.cpp, llama.cpp, etc.)
- Template engine and template path
- Context window, KV cache, GPU offload layer settings
- Expected disk/RAM/VRAM requirements
- Fallback/recovery behavior

Catalog version is independent of Hermes version.  The catalog is
loaded from a JSON file (``profile_catalog.json``) and validated against
a schema at load time.

Usage::

    from huldra_profiles import ProfileCatalog
    catalog = ProfileCatalog.from_file(path)
    for profile in catalog.profiles:
        print(profile.name, profile.id)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CATALOG_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ArtifactRef:
    """Reference to a single artifact (model GGUF, runtime binary, template)."""
    name: str
    path: str  # Relative to HULDRA_HOME or absolute
    sha256: str = ""
    source_url: str = ""
    license: str = ""
    revision: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "source_url": self.source_url,
            "license": self.license,
            "revision": self.revision,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRef":
        return cls(
            name=data["name"],
            path=data["path"],
            sha256=data.get("sha256", ""),
            source_url=data.get("source_url", ""),
            license=data.get("license", ""),
            revision=data.get("revision", ""),
            size_bytes=data.get("size_bytes", 0),
        )


# System reserves: matching huldra_hardware.py
# Profile ResourceRequirements stores "usable" values (what the app needs
# after system reserve).  The manifest (catalog JSON) records "physical-free"
# values (usable + reserve) so users see actual hardware requirements.
_SYSTEM_RESERVED_DISK_GB = 5.0
_SYSTEM_RESERVED_RAM_GB = 2.0
_SYSTEM_RESERVED_VRAM_GB = 0.5


@dataclass
class ResourceRequirements:
    """Declared resource requirements for a profile.

    Internal values are "usable" (what the application needs from
    hardware after system reserve).  When serialised for the manifest
    (catalog JSON), system reserves are added to produce "physical-free"
    values matching huldra_hardware.py semantics.
    """
    min_disk_gb: float = 0.0
    min_ram_gb: float = 0.0
    min_vram_gb: float = 0.0
    recommended_disk_gb: float = 0.0
    recommended_ram_gb: float = 0.0
    recommended_vram_gb: float = 0.0

    def to_dict(self, physical: bool = False) -> dict[str, Any]:
        """Serialise resource requirements.

        When *physical* is True (for catalog/manifest output), system
        reserves are added so the values represent physical-free hardware
        the user needs.  When False (default), usable values are returned
        for internal/recommender use.
        """
        if physical:
            return {
                "min_disk_gb": self.min_disk_gb + _SYSTEM_RESERVED_DISK_GB,
                "min_ram_gb": self.min_ram_gb + _SYSTEM_RESERVED_RAM_GB,
                "min_vram_gb": self.min_vram_gb + _SYSTEM_RESERVED_VRAM_GB,
                "recommended_disk_gb": self.recommended_disk_gb + _SYSTEM_RESERVED_DISK_GB,
                "recommended_ram_gb": self.recommended_ram_gb + _SYSTEM_RESERVED_RAM_GB,
                "recommended_vram_gb": self.recommended_vram_gb + _SYSTEM_RESERVED_VRAM_GB,
            }
        return {
            "min_disk_gb": self.min_disk_gb,
            "min_ram_gb": self.min_ram_gb,
            "min_vram_gb": self.min_vram_gb,
            "recommended_disk_gb": self.recommended_disk_gb,
            "recommended_ram_gb": self.recommended_ram_gb,
            "recommended_vram_gb": self.recommended_vram_gb,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceRequirements":
        """Load resource requirements.

        Accepts both "usable" values (no reserves) and "physical-free"
        values (reserves included).  When ``resource_units`` is
        ``"physical"`` (or reserves are detected), the system reserve is
        subtracted to store usable values internally.
        """
        units = data.get("resource_units", "usable")
        disk = data.get("min_disk_gb", 0.0)
        ram = data.get("min_ram_gb", 0.0)
        vram = data.get("min_vram_gb", 0.0)
        r_disk = data.get("recommended_disk_gb", 0.0)
        r_ram = data.get("recommended_ram_gb", 0.0)
        r_vram = data.get("recommended_vram_gb", 0.0)
        if units == "physical":
            disk -= _SYSTEM_RESERVED_DISK_GB
            ram -= _SYSTEM_RESERVED_RAM_GB
            vram -= _SYSTEM_RESERVED_VRAM_GB
            r_disk -= _SYSTEM_RESERVED_DISK_GB
            r_ram -= _SYSTEM_RESERVED_RAM_GB
            r_vram -= _SYSTEM_RESERVED_VRAM_GB
        return cls(
            min_disk_gb=max(0.0, disk),
            min_ram_gb=max(0.0, ram),
            min_vram_gb=max(0.0, vram),
            recommended_disk_gb=max(0.0, r_disk),
            recommended_ram_gb=max(0.0, r_ram),
            recommended_vram_gb=max(0.0, r_vram),
        )


@dataclass
class RuntimeConfig:
    """Runtime/backend configuration for a profile."""
    backend_type: str = "llama.cpp"  # llama.cpp, ik_llama.cpp, ollama, vllm
    backend_binary: str = ""  # Path to the runtime binary (relative or absolute)
    backend_args: list[str] = field(default_factory=list)
    context_length: int = 4096
    kv_cache_type: str = "f16"
    gpu_offload_layers: int = 0  # 0 = auto, -1 = all layers
    gpu_split: str = ""  # e.g. "auto" or "0.5,0.5"
    threads: int = 0  # 0 = auto
    extra_env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_type": self.backend_type,
            "backend_binary": self.backend_binary,
            "backend_args": self.backend_args,
            "context_length": self.context_length,
            "kv_cache_type": self.kv_cache_type,
            "gpu_offload_layers": self.gpu_offload_layers,
            "gpu_split": self.gpu_split,
            "threads": self.threads,
            "extra_env": self.extra_env,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeConfig":
        return cls(
            backend_type=data.get("backend_type", "llama.cpp"),
            backend_binary=data.get("backend_binary", ""),
            backend_args=data.get("backend_args", []),
            context_length=data.get("context_length", 4096),
            kv_cache_type=data.get("kv_cache_type", "f16"),
            gpu_offload_layers=data.get("gpu_offload_layers", 0),
            gpu_split=data.get("gpu_split", ""),
            threads=data.get("threads", 0),
            extra_env=data.get("extra_env", {}),
        )


@dataclass
class TemplateConfig:
    """Chat template configuration for a profile."""
    template_type: str = "jinja"  # jinja, raw, sharp
    template_path: str = ""  # Path to template file
    template_id: str = ""  # For Sharp v22.4.1 or other named templates

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_type": self.template_type,
            "template_path": self.template_path,
            "template_id": self.template_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TemplateConfig":
        return cls(
            template_type=data.get("template_type", "jinja"),
            template_path=data.get("template_path", ""),
            template_id=data.get("template_id", ""),
        )


@dataclass
class FallbackConfig:
    """Fallback and recovery behavior for a profile."""
    fallback_profiles: list[str] = field(default_factory=list)  # Profile IDs to try if this fails
    retry_count: int = 2
    retry_delay_seconds: float = 5.0
    health_check_url: str = ""
    health_check_timeout: float = 10.0
    auto_download: bool = True
    auto_download_timeout: float = 300.0  # 5 minutes

    def to_dict(self) -> dict[str, Any]:
        return {
            "fallback_profiles": self.fallback_profiles,
            "retry_count": self.retry_count,
            "retry_delay_seconds": self.retry_delay_seconds,
            "health_check_url": self.health_check_url,
            "health_check_timeout": self.health_check_timeout,
            "auto_download": self.auto_download,
            "auto_download_timeout": self.auto_download_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FallbackConfig":
        return cls(
            fallback_profiles=data.get("fallback_profiles", []),
            retry_count=data.get("retry_count", 2),
            retry_delay_seconds=data.get("retry_delay_seconds", 5.0),
            health_check_url=data.get("health_check_url", ""),
            health_check_timeout=data.get("health_check_timeout", 10.0),
            auto_download=data.get("auto_download", True),
            auto_download_timeout=data.get("auto_download_timeout", 300.0),
        )


@dataclass
class Profile:
    """A complete model profile."""
    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    model_name: str = ""
    model_arch: str = ""
    model_family: str = ""  # qwen, gemma, llama, etc.
    role: str = "user-facing"  # "user-facing" or "worker" (sub-agent/optional)
    optional: bool = False  # True for worker/sub-agent entries not in primary catalog

    # Artifacts
    model_artifact: Optional[ArtifactRef] = None
    runtime_artifact: Optional[ArtifactRef] = None
    template_artifact: Optional[ArtifactRef] = None
    auxiliary_artifacts: list[ArtifactRef] = field(default_factory=list)

    # Runtime configuration
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    template: TemplateConfig = field(default_factory=TemplateConfig)

    # Resource requirements
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)

    # Fallback behavior
    fallback: FallbackConfig = field(default_factory=FallbackConfig)

    # Provenance metadata (optional, stored as dicts)
    source: dict = field(default_factory=dict)
    runtime_flags: dict = field(default_factory=dict)

    def to_dict(self, physical: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "model_name": self.model_name,
            "model_arch": self.model_arch,
            "model_family": self.model_family,
            "role": self.role,
            "optional": self.optional,
            "runtime": self.runtime.to_dict(),
            "template": self.template.to_dict(),
            "resources": self.resources.to_dict(physical=physical),
            "fallback": self.fallback.to_dict(),
        }
        if self.model_artifact:
            d["model_artifact"] = self.model_artifact.to_dict()
        if self.runtime_artifact:
            d["runtime_artifact"] = self.runtime_artifact.to_dict()
        if self.template_artifact:
            d["template_artifact"] = self.template_artifact.to_dict()
        if self.auxiliary_artifacts:
            d["auxiliary_artifacts"] = [a.to_dict() for a in self.auxiliary_artifacts]
        if self.source:
            d["source"] = dict(self.source)
        if self.runtime_flags:
            d["runtime_flags"] = dict(self.runtime_flags)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        model_art = None
        if "model_artifact" in data and data["model_artifact"]:
            model_art = ArtifactRef.from_dict(data["model_artifact"])
        runtime_art = None
        if "runtime_artifact" in data and data["runtime_artifact"]:
            runtime_art = ArtifactRef.from_dict(data["runtime_artifact"])
        template_art = None
        if "template_artifact" in data and data["template_artifact"]:
            template_art = ArtifactRef.from_dict(data["template_artifact"])

        aux_arts = []
        for aux_data in data.get("auxiliary_artifacts", []):
            aux_arts.append(ArtifactRef.from_dict(aux_data))

        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            model_name=data.get("model_name", ""),
            model_arch=data.get("model_arch", ""),
            model_family=data.get("model_family", ""),
            role=data.get("role", "user-facing"),
            optional=data.get("optional", False),
            model_artifact=model_art,
            runtime_artifact=runtime_art,
            template_artifact=template_art,
            auxiliary_artifacts=aux_arts,
            runtime=RuntimeConfig.from_dict(data.get("runtime", {})),
            template=TemplateConfig.from_dict(data.get("template", {})),
            resources=ResourceRequirements.from_dict(data.get("resources", {})),
            fallback=FallbackConfig.from_dict(data.get("fallback", {})),
            source=data.get("source", {}),
            runtime_flags=data.get("runtime_flags", {}),
        )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class ProfileCatalogError(Exception):
    """Error loading or validating the profile catalog."""


@dataclass
class ProfileCatalog:
    """Versioned catalog of model profiles.

    The catalog itself carries a version string and a list of profiles.
    Loading validates the schema and rejects duplicate IDs.
    """
    version: str = CATALOG_VERSION
    profiles: list[Profile] = field(default_factory=list)
    _index: dict[str, Profile] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index = {p.id: p for p in self.profiles}

    @property
    def profile_ids(self) -> list[str]:
        return [p.id for p in self.profiles]

    @property
    def primary_profiles(self) -> list[Profile]:
        """Read-only view of user-facing, non-optional profiles."""
        return [p for p in self.profiles if p.role == "user-facing" and not p.optional]

    @property
    def worker_profiles(self) -> list[Profile]:
        """Read-only view of worker/optional profiles."""
        return [p for p in self.profiles if p.role == "worker" or p.optional]

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._index.get(profile_id)

    def add(self, profile: Profile) -> None:
        if profile.id in self._index:
            raise ProfileCatalogError(
                f"Duplicate profile ID: {profile.id}"
            )
        self.profiles.append(profile)
        self._index[profile.id] = profile

    def remove(self, profile_id: str) -> bool:
        before = len(self.profiles)
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        if len(self.profiles) < before:
            self._index.pop(profile_id, None)
            return True
        return False

    def to_dict(self, physical: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "version": self.version,
            "profiles": [p.to_dict(physical=physical) for p in self.profiles],
        }
        if physical:
            d["resource_units"] = "physical"
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileCatalog":
        catalog = cls(
            version=data.get("version", CATALOG_VERSION),
        )
        resource_units = data.get("resource_units", "usable")
        for p_data in data.get("profiles", []):
            # Propagate catalog-level resource_units into each profile's
            # resources dict so ResourceRequirements.from_dict() knows
            # whether to subtract system reserves.
            if resource_units == "physical" and "resources" in p_data:
                p_data = dict(p_data)
                res = dict(p_data.get("resources", {}))
                res["resource_units"] = "physical"
                p_data["resources"] = res
            try:
                profile = Profile.from_dict(p_data)
                catalog.add(profile)
            except ProfileCatalogError:
                raise
            except Exception as e:
                raise ProfileCatalogError(
                    f"Invalid profile data: {e}"
                ) from e
        return catalog

    @classmethod
    def from_file(cls, path: Path) -> "ProfileCatalog":
        """Load a profile catalog from a JSON file.

        Validates the version and profile schema.
        """
        if not path.exists():
            raise ProfileCatalogError(f"Catalog file not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ProfileCatalogError(
                f"Invalid JSON in catalog: {e}"
            ) from e

        catalog = cls.from_dict(data)
        logger.info(
            "Loaded profile catalog v%s with %d profiles from %s",
            catalog.version,
            len(catalog.profiles),
            path,
        )
        return catalog

    def save(self, path: Path) -> None:
        """Save the catalog to a JSON file.

        Resource values are written as physical-free (usable + system
        reserve) matching huldra_hardware.py semantics.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(physical=True), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Saved profile catalog v%s to %s", self.version, path)

    def validate(self) -> list[str]:
        """Validate the catalog. Returns list of errors (empty = valid)."""
        errors = []
        ids_seen: set[str] = set()
        for profile in self.profiles:
            if profile.id in ids_seen:
                errors.append(f"Duplicate profile ID: {profile.id}")
            ids_seen.add(profile.id)

            if not profile.name:
                errors.append(f"Profile {profile.id}: missing name")
            if not profile.model_name:
                errors.append(f"Profile {profile.id}: missing model_name")
            if not profile.runtime.backend_type:
                errors.append(f"Profile {profile.id}: missing runtime.backend_type")
            if profile.resources.min_vram_gb < 0:
                errors.append(f"Profile {profile.id}: negative min_vram_gb")
            if profile.resources.min_ram_gb < 0:
                errors.append(f"Profile {profile.id}: negative min_ram_gb")

            # Validate fallback references exist
            for fb_id in profile.fallback.fallback_profiles:
                if fb_id not in ids_seen and fb_id not in self._index:
                    # Check if it exists later in the list
                    later = any(p.id == fb_id for p in self.profiles if p.id != profile.id)
                    if not later:
                        errors.append(
                            f"Profile {profile.id}: fallback profile {fb_id} not found"
                        )

        return errors


# ---------------------------------------------------------------------------
# Default V1 catalog (hardcoded)
# ---------------------------------------------------------------------------

def create_v1_default_catalog() -> ProfileCatalog:
    """Create the default V1 profile catalog with exactly three profiles.

    These profiles are declarative.  Artifact paths are relative to
    ``$HULDRA_HOME/runtimes/`` (for binaries) and ``$HULDRA_HOME/models/``
    (for GGUFs).  Templates live under ``$HULDRA_HOME/templates/``.
    """
    catalog = ProfileCatalog(version=CATALOG_VERSION)

    # Profile 1: Qwen3.6-35B-A3B / APEX I-Compact GGUF / ik_llama.cpp
    catalog.add(Profile(
        id="qwen36-35b-apex",
        name="Qwen 3.6 35B A3B (APEX I-Compact)",
        description=(
            "Qwen 3.6 35B-A3B with APEX I-Compact GGUF quantization, "
            "running on ik_llama.cpp with the Sharp v22.4.1 chat template."
        ),
        version="1.0.0",
        model_name="Qwen3.6-35B-A3B-APEX-I-Compact",
        model_arch="qwen3",
        model_family="qwen",
        source={
            "upstream_repo": "mudler/Qwen3.6-35B-A3B-APEX-GGUF",
            "upstream_url": "https://huggingface.co/mudler/Qwen3.6-35B-A3B-APEX-GGUF",
            "upstream_revision": "316efc983b0d8d41290ceb4ad31bd9a66b6c54e8",
            "license": "Apache-2.0",
        },
        model_artifact=ArtifactRef(
            name="Qwen3.6-35B-A3B-APEX-I-Compact.gguf",
            path="Models/Qwen3.6-35B-A3B-APEX-I-Compact/Qwen3.6-35B-A3B-APEX-I-Compact.gguf",
            sha256="50e1122946854f2272b44d466c03d17d410d3f02dcd1c021a1f29f6b384a7126",
            source_url="https://huggingface.co/mudler/Qwen3.6-35B-A3B-APEX-GGUF/resolve/316efc983b0d8d41290ceb4ad31bd9a66b6c54e8/Qwen3.6-35B-A3B-APEX-I-Compact.gguf",
            license="Apache-2.0",
            revision="316efc983b0d8d41290ceb4ad31bd9a66b6c54e8",
            size_bytes=17293089472,
        ),
        runtime_artifact=ArtifactRef(
            name="ik_llama-server",
            path="runtimes/ik_llama/main-b5236-b56bd59/llama-server.exe",
            sha256="",
            source_url="https://github.com/Thireus/ik_llama.cpp/releases/tag/main-b5236-b56bd59",
            license="MIT",
            revision="main-b5236-b56bd59",
        ),
        template_artifact=ArtifactRef(
            name="sharp-v22.4.1",
            path="Models/Qwen3.6-35B-A3B-APEX-I-Compact/template/chat_template.jinja",
            sha256="AE8FC6F688656083095FA39855F90A761A10ADE61D7B21D6B761F5651F100473",
            source_url="https://huggingface.co/peculiar-ragdoll/Qwen-Sharp-Chat-Templates",
            license="MIT",
            revision="5cb86e230acb03ffd992b841ecb12318a518e374",
            size_bytes=29686,
        ),
        runtime=RuntimeConfig(
            backend_type="ik_llama.cpp",
            backend_binary="runtimes/ik_llama/main-b5236-b56bd59/llama-server.exe",
            backend_args=[
                "--ctx-size", "8192",
                "--n-gpu-layers", "99",
                "--host", "127.0.0.1",
                "--port", "8080",
            ],
            context_length=8192,
            kv_cache_type="f16",
            gpu_offload_layers=99,
            threads=0,
        ),
        template=TemplateConfig(
            template_type="jinja",
            template_path="Models/Qwen3.6-35B-A3B-APEX-I-Compact/template/chat_template.jinja",
            template_id="sharp-v22.4.1",
        ),
        resources=ResourceRequirements(
            min_disk_gb=25.0,
            min_ram_gb=16.0,
            min_vram_gb=8.0,
            recommended_disk_gb=30.0,
            recommended_ram_gb=24.0,
            recommended_vram_gb=12.0,
        ),
        fallback=FallbackConfig(
            fallback_profiles=["gemma4-e4b"],
            retry_count=2,
            retry_delay_seconds=5.0,
        ),
    ))

    # Profile 2: Gemma 4 E4B / Google QAT Q4_0 GGUF
    catalog.add(Profile(
        id="gemma4-e4b",
        name="Gemma 4 E4B (Google QAT)",
        description=(
            "Gemma 4 E4B with official Google QAT Q4_0 GGUF quantization, "
            "using the official Google Jinja chat template."
        ),
        version="1.0.0",
        model_name="gemma-4-E4B-it-qat-q4_0",
        model_arch="gemma4",
        model_family="gemma",
        source={
            "upstream_repo": "google/gemma-4-E4B-it-qat-q4_0-gguf",
            "upstream_url": "https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf",
            "upstream_revision": "4b4a2c1d584be7264f87aac328a1bc739ce81b6c",
            "license": "gemma-terms-of-use",
        },
        model_artifact=ArtifactRef(
            name="gemma-4-E4B_q4_0-it.gguf",
            path="Models/Gemma4-E4B/google-qat-q4_0/gemma-4-E4B_q4_0-it.gguf",
            sha256="676C35070DB6DBE52F93E9C864EE0FBA4EDDEA94B9C875D9CB10DAFF453FBAEE",
            source_url="https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/gemma-4-E4B_q4_0-it.gguf",
            license="gemma-terms-of-use",
            revision="4b4a2c1d584be7264f87aac328a1bc739ce81b6c",
            size_bytes=5154941280,
        ),
        runtime_artifact=ArtifactRef(
            name="llama-server",
            path="runtimes/b10793-cuda12.4/llama-server.exe",
            sha256="ff9bada956f20c4fc8e6f54beecc68bd104a5e903c2bc362239ae9995d2c9658",
            source_url="https://github.com/ggml-org/llama.cpp/releases/tag/b10793",
            license="MIT",
            revision="d230ddd763ffe27781c7ffd237ea78b639b36b6d",
        ),
        template_artifact=ArtifactRef(
            name="gemma4-chat-template",
            path="Models/Gemma4-E4B/template/chat_template.jinja",
            sha256="0A2C8073C878AB1DA004BEE933A998606537BBB62016310352C7285C3F01C5B5",
            source_url="https://huggingface.co/google/gemma-4-E4B-it/resolve/ee0ef6023621cff504d758262d4e04895a5af4a2/tokenizer_config.json",
            license="gemma-terms-of-use",
            revision="ee0ef6023621cff504d758262d4e04895a5af4a2",
        ),
        runtime=RuntimeConfig(
            backend_type="llama.cpp",
            backend_binary="runtimes/b10793-cuda12.4/llama-server.exe",
            backend_args=[
                "--ctx-size", "4096",
                "--n-gpu-layers", "99",
                "--host", "127.0.0.1",
                "--port", "8080",
            ],
            context_length=4096,
            kv_cache_type="f16",
            gpu_offload_layers=99,
            threads=0,
        ),
        template=TemplateConfig(
            template_type="jinja",
            template_path="Models/Gemma4-E4B/template/chat_template.jinja",
        ),
        resources=ResourceRequirements(
            min_disk_gb=5.0,
            min_ram_gb=8.0,
            min_vram_gb=4.0,
            recommended_disk_gb=8.0,
            recommended_ram_gb=16.0,
            recommended_vram_gb=6.0,
        ),
        fallback=FallbackConfig(
            fallback_profiles=[],
            retry_count=2,
            retry_delay_seconds=5.0,
        ),
    ))

    # Profile 3: Qwen3.8-27B / ggml-org llama.cpp-native Q4_K_M + MTP Q4_0
    catalog.add(Profile(
        id="qwen38-27b",
        name="Qwen 3.8 27B (ggml-org llama.cpp)",
        description=(
            "Qwen 3.8 27B with ggml-org llama.cpp-native Q4_K_M GGUF + "
            "MTP Q4_0, running on current Windows/CUDA llama.cpp. "
            "Tolerant of asset handoff completing later; fails closed if "
            "model is not verified installed."
        ),
        version="1.0.0",
        model_name="Qwen3.8-27B-Q4_K_M",
        model_arch="qwen3_5",
        model_family="qwen",
        source={
            "upstream_repo": "Qwen/Qwen3.8-27B",
            "upstream_url": "https://huggingface.co/Qwen/Qwen3.8-27B",
            "upstream_revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
            "quantization_repo": "ggml-org/Qwen3.8-27B-GGUF",
            "quantization_revision": "0669b98607d47046c7c2b3f801011d54a08cfccf",
            "license": "Apache-2.0",
        },
        model_artifact=ArtifactRef(
            name="Qwen3.8-27B-Q4_K_M.gguf",
            path="Models/Qwen3.8-27B/Qwen3.8-27B-Q4_K_M.gguf",
            sha256="31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34",
            source_url="https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/0669b98607d47046c7c2b3f801011d54a08cfccf/Qwen3.8-27B-Q4_K_M.gguf",
            license="Apache-2.0",
            revision="0669b98607d47046c7c2b3f801011d54a08cfccf",
            size_bytes=18973870432,
        ),
        runtime_artifact=ArtifactRef(
            name="llama-server",
            path="runtimes/b10793-cuda12.4/llama-server.exe",
            sha256="ff9bada956f20c4fc8e6f54beecc68bd104a5e903c2bc362239ae9995d2c9658",
            source_url="https://github.com/ggml-org/llama.cpp/releases/tag/b10793",
            license="MIT",
            revision="d230ddd763ffe27781c7ffd237ea78b639b36b6d",
        ),
        template_artifact=ArtifactRef(
            name="qwen38-chat-template",
            path="Models/Qwen3.8-27B/qwen38_chat_template.jinja",
            sha256="4d34c89ef6589bcc9f9d3ffe6ad0122085a7cbd28d7a2e00c24b4973d3c1efc9",
            source_url="https://huggingface.co/Qwen/Qwen3.8-27B/resolve/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/tokenizer_config.json",
            license="Apache-2.0",
            revision="1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
            size_bytes=9121,
        ),
        auxiliary_artifacts=[
            ArtifactRef(
                name="mtp-Qwen3.8-27B-Q4_0.gguf",
                path="Models/Qwen3.8-27B/mtp-Qwen3.8-27B-Q4_0.gguf",
                sha256="051a1764cff8c4f3ee6ae8b00593a0364c7539c67fa50ffc58f3f96509fca38e",
                source_url="https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/0669b98607d47046c7c2b3f801011d54a08cfccf/mtp-Qwen3.8-27B-Q4_0.gguf",
                license="Apache-2.0",
                revision="0669b98607d47046c7c2b3f801011d54a08cfccf",
                size_bytes=1680271648,
            ),
        ],
        runtime=RuntimeConfig(
            backend_type="llama.cpp",
            backend_binary="runtimes/b10793-cuda12.4/llama-server.exe",
            backend_args=[
                "--ctx-size", "8192",
                "--n-gpu-layers", "99",
                "--host", "127.0.0.1",
                "--port", "8080",
                "--mlock",
            ],
            context_length=8192,
            kv_cache_type="f16",
            gpu_offload_layers=99,
            threads=0,
        ),
        template=TemplateConfig(
            template_type="jinja",
            template_path="Models/Qwen3.8-27B/qwen38_chat_template.jinja",
        ),
        resources=ResourceRequirements(
            min_disk_gb=20.0,
            min_ram_gb=16.0,
            min_vram_gb=8.0,
            recommended_disk_gb=25.0,
            recommended_ram_gb=24.0,
            recommended_vram_gb=12.0,
        ),
        fallback=FallbackConfig(
            fallback_profiles=["gemma4-e4b"],
            retry_count=2,
            retry_delay_seconds=5.0,
            auto_download=True,
        ),
    ))

    # Optional worker/sub-agent: Ling 3.0 Tiny
    # NOT a primary V1 profile. Clearly optional, for sub-agent/worker use only.
    catalog.add(Profile(
        id="ling30-tiny-worker",
        name="Ling 3.0 Tiny (worker/sub-agent, Q6_K_L)",
        description=(
            "Official InclusionAI Ling 3.0 Tiny staged as a trusted Bartowski "
            "Q6_K_L GGUF. Optional worker-only lane for extraction, classification, "
            "normalization, context pruning, simple inspection, and bounded scripting; "
            "not selectable as the user's main assistant."
        ),
        version="1.0.0",
        model_name="Ling-3.0-tiny-Q6_K_L",
        model_arch="bailingmoe3",
        model_family="ling",
        role="worker",
        optional=True,
        source={
            "upstream_repo": "inclusionAI/Ling-3.0-tiny",
            "upstream_url": "https://huggingface.co/inclusionAI/Ling-3.0-tiny",
            "upstream_revision": "e3a47d5b986e7141b6efd62597d598ebb392060d",
            "license": "MIT",
            "quantization_repo": "bartowski/Ling-3.0-tiny-GGUF",
            "quantization_url": "https://huggingface.co/bartowski/Ling-3.0-tiny-GGUF",
            "quantization_revision": "ea072726af0d2e8ba325b2f90fc0efa762105a91",
            "quantizer": "bartowski",
            "abliterated": False,
        },
        runtime_flags={
            "jinja": True,
            "flash_attn": "auto",
            "task_scope": "bounded_worker_only",
        },
        model_artifact=ArtifactRef(
            name="Ling-3.0-tiny-Q6_K_L.gguf",
            path="Models/Ling3-Tiny/gguf/Ling-3.0-tiny-Q6_K_L.gguf",
            sha256="f0cddaa11527eb1e486cf957d929ff54e3691c0d6495d019a4132b7a85905a6a",
            source_url="https://huggingface.co/bartowski/Ling-3.0-tiny-GGUF/resolve/ea072726af0d2e8ba325b2f90fc0efa762105a91/Ling-3.0-tiny-Q6_K_L.gguf",
            license="MIT",
            revision="ea072726af0d2e8ba325b2f90fc0efa762105a91",
            size_bytes=6956021056,
        ),
        runtime_artifact=ArtifactRef(
            name="llama-server",
            path="runtimes/b10793-cuda12.4/llama-server.exe",
            sha256="ff9bada956f20c4fc8e6f54beecc68bd104a5e903c2bc362239ae9995d2c9658",
            source_url="https://github.com/ggml-org/llama.cpp/releases/tag/b10793",
            license="MIT",
            revision="d230ddd763ffe27781c7ffd237ea78b639b36b6d",
        ),
        template_artifact=ArtifactRef(
            name="ling3-official-chat-template",
            path="Models/Ling3-Tiny/official-source/chat_template.jinja",
            sha256="eb6226c94ae38058f875d159f86a206b3a165828c0e7d6bda664ae14667f798a",
            source_url="https://huggingface.co/inclusionAI/Ling-3.0-tiny/resolve/e3a47d5b986e7141b6efd62597d598ebb392060d/chat_template.jinja",
            license="MIT",
            revision="e3a47d5b986e7141b6efd62597d598ebb392060d",
        ),
        runtime=RuntimeConfig(
            backend_type="llama.cpp",
            backend_binary="runtimes/b10793-cuda12.4/llama-server.exe",
            backend_args=[
                "--ctx-size", "8192",
                "--n-gpu-layers", "99",
                "--host", "127.0.0.1",
                "--port", "8081",
                "--jinja",
                "--flash-attn", "auto",
                "--alias", "Ling-3.0-tiny-Q6_K_L",
            ],
            context_length=8192,
            kv_cache_type="f16",
            gpu_offload_layers=99,
            threads=0,
        ),
        template=TemplateConfig(
            template_type="jinja",
            template_path="Models/Ling3-Tiny/official-source/chat_template.jinja",
            template_id="ling3-official-upstream",
        ),
        resources=ResourceRequirements(
            min_disk_gb=8.0,
            min_ram_gb=8.0,
            min_vram_gb=7.0,
            recommended_disk_gb=12.0,
            recommended_ram_gb=12.0,
            recommended_vram_gb=8.0,
        ),
        fallback=FallbackConfig(
            fallback_profiles=[],
            retry_count=1,
            retry_delay_seconds=3.0,
            auto_download=False,  # Worker entry: staged assets only
        ),
    ))

    return catalog
