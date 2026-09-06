"""
V1 Profile Catalog, Hardware Detection, and Recommender Tests.

Tests for:
- Profile catalog schema (versioned, three profiles, validation)
- Profile artifact and resource declarations
- Hardware detection (deterministic, no benchmarks)
- Recommender fit derivation (from declared requirements + headroom)
- Manual override with clear fit/asset errors
- Catalog load/save roundtrip
- Fallback profile references

Run: python -m pytest tests/test_v1_profiles.py -v
"""
import json
import os
import pathlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure source/ is on the path for imports
_HERE = pathlib.Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "source"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))


# ============================================================================
# Profile Catalog Tests
# ============================================================================

class TestProfileCatalog:
    """Test ProfileCatalog, Profile, ArtifactRef, ResourceRequirements."""

    def test_catalog_version(self):
        from huldra_profiles import ProfileCatalog, CATALOG_VERSION
        catalog = ProfileCatalog()
        assert catalog.version == CATALOG_VERSION

    def test_default_catalog_has_four_profiles(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        assert len(catalog.profiles) == 4

    def test_default_catalog_profile_ids(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        ids = catalog.profile_ids
        assert "qwen36-35b-apex" in ids
        assert "gemma4-e4b" in ids
        assert "qwen38-27b" in ids
        assert "ling30-tiny-worker" in ids

    def test_catalog_get_by_id(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        assert p is not None
        assert p.name == "Gemma 4 E4B (Google QAT)"
        assert catalog.get("nonexistent") is None

    def test_catalog_add_duplicate_raises(self):
        from huldra_profiles import ProfileCatalog, Profile, ProfileCatalogError
        catalog = ProfileCatalog()
        catalog.add(Profile(id="a", name="A"))
        with pytest.raises(ProfileCatalogError, match="Duplicate"):
            catalog.add(Profile(id="a", name="A2"))

    def test_catalog_remove(self):
        from huldra_profiles import ProfileCatalog, Profile
        catalog = ProfileCatalog()
        catalog.add(Profile(id="a", name="A"))
        assert catalog.remove("a") is True
        assert catalog.remove("a") is False
        assert len(catalog.profiles) == 0

    def test_catalog_validate_empty(self):
        from huldra_profiles import ProfileCatalog
        catalog = ProfileCatalog()
        errors = catalog.validate()
        assert errors == []

    def test_catalog_validate_valid(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        errors = catalog.validate()
        assert errors == []

    def test_catalog_validate_duplicate_id(self):
        from huldra_profiles import ProfileCatalog, Profile
        catalog = ProfileCatalog()
        # Manually bypass add() to create a duplicate
        catalog.profiles.append(Profile(id="x", name="X1"))
        catalog.profiles.append(Profile(id="x", name="X2"))
        errors = catalog.validate()
        assert any("Duplicate" in e for e in errors)

    def test_catalog_validate_missing_name(self):
        from huldra_profiles import ProfileCatalog, Profile
        catalog = ProfileCatalog()
        catalog.add(Profile(id="p1", name="", model_name="m"))
        errors = catalog.validate()
        assert any("missing name" in e for e in errors)

    def test_catalog_validate_missing_model_name(self):
        from huldra_profiles import ProfileCatalog, Profile
        catalog = ProfileCatalog()
        catalog.add(Profile(id="p1", name="P1", model_name=""))
        errors = catalog.validate()
        assert any("missing model_name" in e for e in errors)

    def test_catalog_validate_fallback_not_found(self):
        from huldra_profiles import ProfileCatalog, Profile, FallbackConfig
        catalog = ProfileCatalog()
        catalog.add(Profile(
            id="a", name="A",
            fallback=FallbackConfig(fallback_profiles=["nonexistent"]),
        ))
        errors = catalog.validate()
        assert any("nonexistent" in e and "fallback" in e for e in errors)

    def test_catalog_save_load_roundtrip(self):
        from huldra_profiles import create_v1_default_catalog, ProfileCatalog
        original = create_v1_default_catalog()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            original.save(path)
            loaded = ProfileCatalog.from_file(path)
            assert loaded.version == original.version
            assert len(loaded.profiles) == len(original.profiles)
            for orig_p, loaded_p in zip(original.profiles, loaded.profiles):
                assert orig_p.id == loaded_p.id
                assert orig_p.name == loaded_p.name

    def test_catalog_load_not_found(self):
        from huldra_profiles import ProfileCatalog, ProfileCatalogError
        with pytest.raises(ProfileCatalogError, match="not found"):
            ProfileCatalog.from_file(Path("/nonexistent/catalog.json"))

    def test_catalog_load_invalid_json(self):
        from huldra_profiles import ProfileCatalog, ProfileCatalogError
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text("NOT JSON {{{")
            with pytest.raises(ProfileCatalogError, match="Invalid JSON"):
                ProfileCatalog.from_file(path)


# ============================================================================
# Profile Data Model Tests
# ============================================================================

class TestProfileDataModel:
    """Test Profile, ArtifactRef, ResourceRequirements, RuntimeConfig."""

    def test_profile_to_dict_roundtrip(self):
        from huldra_profiles import Profile, ArtifactRef, RuntimeConfig, ResourceRequirements
        p = Profile(
            id="test",
            name="Test Profile",
            model_name="test-model",
            model_arch="llama",
            model_family="llama",
            model_artifact=ArtifactRef(
                name="model.gguf",
                path="models/model.gguf",
                sha256="abc123",
                license="MIT",
            ),
            runtime=RuntimeConfig(
                backend_type="llama.cpp",
                context_length=4096,
                gpu_offload_layers=99,
            ),
            resources=ResourceRequirements(
                min_disk_gb=10.0,
                min_ram_gb=8.0,
                min_vram_gb=4.0,
            ),
        )
        d = p.to_dict()
        p2 = Profile.from_dict(d)
        assert p2.id == "test"
        assert p2.model_artifact is not None
        assert p2.model_artifact.sha256 == "abc123"
        assert p2.runtime.context_length == 4096
        assert p2.resources.min_vram_gb == 4.0

    def test_artifact_ref_defaults(self):
        from huldra_profiles import ArtifactRef
        a = ArtifactRef(name="x", path="y")
        assert a.sha256 == ""
        assert a.license == ""
        assert a.size_bytes == 0

    def test_resource_requirements_defaults(self):
        from huldra_profiles import ResourceRequirements
        r = ResourceRequirements()
        assert r.min_disk_gb == 0.0
        assert r.min_ram_gb == 0.0
        assert r.min_vram_gb == 0.0

    def test_fallback_config_defaults(self):
        from huldra_profiles import FallbackConfig
        fb = FallbackConfig()
        assert fb.retry_count == 2
        assert fb.auto_download is True


# ============================================================================
# Profile Artifact Verification Tests
# ============================================================================

class TestProfileArtifacts:
    """Verify each V1 profile has the declared artifacts."""

    def test_primary_profiles_are_user_facing(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        for pid in ["qwen36-35b-apex", "gemma4-e4b", "qwen38-27b"]:
            p = catalog.get(pid)
            assert p is not None
            assert p.role == "user-facing"
            assert p.optional is False

    def test_qwen36_has_model_artifact(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen36-35b-apex")
        assert p is not None
        assert p.model_artifact is not None
        assert "Qwen" in p.model_artifact.name or "qwen" in p.model_artifact.name.lower()
        assert p.model_artifact.license == "Apache-2.0"

    def test_qwen36_uses_ik_llama(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen36-35b-apex")
        assert p is not None
        assert p.runtime.backend_type == "ik_llama.cpp"
        assert "ik_llama" in p.runtime.backend_binary

    def test_qwen36_uses_sharp_template(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen36-35b-apex")
        assert p is not None
        assert p.template.template_type == "jinja"
        assert "sharp" in p.template.template_id

    def test_gemma4_has_model_artifact(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        assert p is not None
        assert p.model_artifact is not None
        assert "gemma" in p.model_artifact.name.lower()
        assert "gemma" in p.model_artifact.license.lower()

    def test_gemma4_uses_google_jinja(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        assert p is not None
        assert p.template.template_type == "jinja"
        assert "Gemma4" in p.template.template_path or "gemma4" in p.template.template_path.lower()

    def test_gemma4_smallest_requirements(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        assert p is not None
        assert p.resources.min_disk_gb <= 5.0
        assert p.resources.min_ram_gb <= 8.0
        assert p.resources.min_vram_gb <= 4.0

    def test_qwen38_has_model_artifact(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen38-27b")
        assert p is not None
        assert p.model_artifact is not None
        assert "Qwen" in p.model_artifact.name or "qwen" in p.model_artifact.name.lower()

    def test_qwen38_uses_llama_cpp(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen38-27b")
        assert p is not None
        assert p.runtime.backend_type == "llama.cpp"
        assert "llama-server" in p.runtime.backend_binary

    def test_qwen38_fallback_to_gemma(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen38-27b")
        assert p is not None
        assert "gemma4-e4b" in p.fallback.fallback_profiles


# ============================================================================
# Optional Worker Profile Tests (Ling 3.0 Tiny)
# ============================================================================

class TestOptionalWorkerProfile:
    """Static/schema tests for the optional Ling 3.0 Tiny worker entry.

    No benchmarking, no model research — schema/role/fallback only.
    """

    def test_ling_worker_exists(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None

    def test_ling_worker_role_is_worker(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.role == "worker"

    def test_ling_worker_is_optional(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.optional is True

    def test_ling_worker_not_user_facing(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.role != "user-facing"

    def test_ling_worker_has_model_artifact(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.model_artifact is not None
        assert "ling" in p.model_artifact.name.lower()

    def test_ling_worker_has_runtime(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.runtime.backend_type == "llama.cpp"
        # Worker uses different port to avoid collision
        assert "--port" in p.runtime.backend_args
        port_idx = p.runtime.backend_args.index("--port")
        assert p.runtime.backend_args[port_idx + 1] == "8081"

    def test_ling_worker_no_auto_download(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.fallback.auto_download is False

    def test_ling_worker_smaller_requirements(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        # Ling Q6_K_L has honest 7/8/8 GB floors — larger than Gemma but
        # still a worker: optional, not user-facing, no fallback chain.
        assert p.role == "worker"
        assert p.optional is True
        assert p.resources.min_vram_gb == 7.0
        assert p.resources.min_ram_gb == 8.0
        assert p.resources.min_disk_gb == 8.0

    def test_ling_worker_provenance_and_non_abliterated(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        d = p.to_dict()
        # source is stored as a dict on the Profile dataclass
        src = d.get("source", {})
        assert src.get("upstream_repo") == "inclusionAI/Ling-3.0-tiny"
        assert src.get("upstream_revision") == "e3a47d5b986e7141b6efd62597d598ebb392060d"
        assert src.get("quantization_repo") == "bartowski/Ling-3.0-tiny-GGUF"
        assert src.get("abliterated") is False
        assert p.model_artifact.license == "MIT"
        assert p.model_artifact.sha256 == "f0cddaa11527eb1e486cf957d929ff54e3691c0d6495d019a4132b7a85905a6a"
        assert p.model_artifact.size_bytes == 6956021056
        assert p.template_artifact.sha256 == "eb6226c94ae38058f875d159f86a206b3a165828c0e7d6bda664ae14667f798a"

    def test_primary_catalog_remains_three_profiles(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        assert [p.id for p in catalog.primary_profiles] == [
            "qwen36-35b-apex", "gemma4-e4b", "qwen38-27b"
        ]
        assert [p.id for p in catalog.worker_profiles] == ["ling30-tiny-worker"]

    def test_ling_worker_no_fallback_chain(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        assert p.fallback.fallback_profiles == []


# ============================================================================
# Auxiliary Artifacts / MTP Binding Tests
# ============================================================================

class TestAuxiliaryArtifacts:
    """Test auxiliary_artifacts field on Profile for MTP and other secondary artifacts."""

    def test_auxiliary_artifacts_defaults_empty(self):
        from huldra_profiles import Profile
        p = Profile(id="x", name="X")
        assert p.auxiliary_artifacts == []

    def test_qwen38_has_mtp_auxiliary_artifact(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen38-27b")
        assert p is not None
        assert len(p.auxiliary_artifacts) == 1
        mtp = p.auxiliary_artifacts[0]
        assert mtp.name == "mtp-Qwen3.8-27B-Q4_0.gguf"
        assert "mtp-Qwen3.8-27B-Q4_0.gguf" in mtp.path

    def test_mtp_artifact_metadata(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen38-27b")
        mtp = p.auxiliary_artifacts[0]
        assert mtp.sha256 == "051a1764cff8c4f3ee6ae8b00593a0364c7539c67fa50ffc58f3f96509fca38e"
        assert mtp.size_bytes == 1680271648
        assert mtp.license == "Apache-2.0"
        assert mtp.revision == "0669b98607d47046c7c2b3f801011d54a08cfccf"

    def test_mtp_not_in_other_profiles(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        for pid in ["qwen36-35b-apex", "gemma4-e4b", "ling30-tiny-worker"]:
            p = catalog.get(pid)
            assert p is not None
            assert p.auxiliary_artifacts == []

    def test_auxiliary_artifacts_roundtrip(self):
        from huldra_profiles import Profile, ArtifactRef, ProfileCatalog, create_v1_default_catalog
        original = create_v1_default_catalog()
        p = original.get("qwen38-27b")
        d = p.to_dict()
        assert "auxiliary_artifacts" in d
        assert len(d["auxiliary_artifacts"]) == 1
        p2 = Profile.from_dict(d)
        assert len(p2.auxiliary_artifacts) == 1
        assert p2.auxiliary_artifacts[0].sha256 == "051a1764cff8c4f3ee6ae8b00593a0364c7539c67fa50ffc58f3f96509fca38e"
        assert p2.auxiliary_artifacts[0].size_bytes == 1680271648

    def test_catalog_roundtrip_preserves_auxiliary(self):
        from huldra_profiles import create_v1_default_catalog, ProfileCatalog
        import tempfile
        from pathlib import Path
        original = create_v1_default_catalog()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            original.save(path)
            loaded = ProfileCatalog.from_file(path)
            p = loaded.get("qwen38-27b")
            assert p is not None
            assert len(p.auxiliary_artifacts) == 1
            assert p.auxiliary_artifacts[0].name == "mtp-Qwen3.8-27B-Q4_0.gguf"

    def test_no_auxiliary_artifacts_omitted_from_dict(self):
        from huldra_profiles import Profile
        p = Profile(id="x", name="X")
        d = p.to_dict()
        assert "auxiliary_artifacts" not in d

    def test_empty_auxiliary_artifacts_omitted_from_dict(self):
        from huldra_profiles import Profile
        p = Profile(id="x", name="X", auxiliary_artifacts=[])
        d = p.to_dict()
        assert "auxiliary_artifacts" not in d

    def test_ling_worker_to_dict_roundtrip(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        p = catalog.get("ling30-tiny-worker")
        assert p is not None
        d = p.to_dict()
        assert d["role"] == "worker"
        assert d["optional"] is True
        from huldra_profiles import Profile
        p2 = Profile.from_dict(d)
        assert p2.role == "worker"
        assert p2.optional is True

    def test_catalog_validate_includes_ling(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        errors = catalog.validate()
        # Ling entry should not cause validation errors
        ling_errors = [e for e in errors if "ling" in e.lower()]
        assert ling_errors == []


# ============================================================================
# Hardware Detection Tests
# ============================================================================

class TestHardwareDetection:
    """Test hardware detection functions (deterministic, no benchmarks)."""

    def test_hardware_profile_defaults(self):
        from huldra_hardware import HardwareProfile
        hw = HardwareProfile()
        assert hw.gpu.vendor == "unknown"
        assert hw.ram_total_gb == 0.0
        assert hw.usable_vram_gb == 0.0

    def test_hardware_profile_to_dict_roundtrip(self):
        from huldra_hardware import HardwareProfile, GPUInfo, StorageInfo
        hw = HardwareProfile(
            gpu=GPUInfo(name="RTX 4090", vram_total_gb=24.0, vendor="nvidia"),
            ram_total_gb=32.0,
            ram_available_gb=24.0,
            storage=StorageInfo(path="C:\\", total_gb=1000.0, free_gb=500.0),
            usable_vram_gb=23.5,
            usable_ram_gb=22.0,
            usable_disk_gb=495.0,
        )
        d = hw.to_dict()
        hw2 = HardwareProfile.from_dict(d)
        assert hw2.gpu.name == "RTX 4090"
        assert hw2.gpu.vram_total_gb == 24.0
        assert hw2.ram_total_gb == 32.0
        assert hw2.usable_vram_gb == 23.5

    def test_detect_hardware_returns_profile(self):
        from huldra_hardware import detect_hardware
        hw = detect_hardware()
        assert isinstance(hw.ram_total_gb, float)
        assert isinstance(hw.gpu.vendor, str)
        assert hw.detect_time > 0

    def test_detect_hardware_os_info(self):
        from huldra_hardware import detect_hardware
        hw = detect_hardware()
        assert hw.os_name in ("Windows", "Linux", "Darwin")
        assert hw.python_version != ""

    def test_usable_vram_subtracts_reserved(self):
        from huldra_hardware import HardwareProfile, GPUInfo, SYSTEM_RESERVED_VRAM_GB
        hw = HardwareProfile(gpu=GPUInfo(vram_total_gb=8.0, vendor="nvidia"))
        hw.usable_vram_gb = max(0.0, hw.gpu.vram_total_gb - SYSTEM_RESERVED_VRAM_GB)
        assert hw.usable_vram_gb < 8.0
        assert hw.usable_vram_gb == pytest.approx(8.0 - SYSTEM_RESERVED_VRAM_GB)

    def test_usable_ram_subtracts_reserved(self):
        from huldra_hardware import HardwareProfile, SYSTEM_RESERVED_RAM_GB
        hw = HardwareProfile(ram_total_gb=16.0, ram_available_gb=12.0)
        hw.usable_ram_gb = max(0.0, hw.ram_available_gb - SYSTEM_RESERVED_RAM_GB)
        assert hw.usable_ram_gb == pytest.approx(12.0 - SYSTEM_RESERVED_RAM_GB)

    def test_usable_disk_subtracts_reserved(self):
        from huldra_hardware import HardwareProfile, SYSTEM_RESERVED_DISK_GB
        hw = HardwareProfile()
        hw.storage = type(hw.storage)(free_gb=100.0)
        hw.usable_disk_gb = max(0.0, hw.storage.free_gb - SYSTEM_RESERVED_DISK_GB)
        assert hw.usable_disk_gb == pytest.approx(100.0 - SYSTEM_RESERVED_DISK_GB)

    def test_no_negative_usable(self):
        from huldra_hardware import HardwareProfile, GPUInfo
        hw = HardwareProfile(gpu=GPUInfo(vram_total_gb=0.1))
        usable = max(0.0, hw.gpu.vram_total_gb - 0.5)
        assert usable >= 0.0

    def test_save_load_hardware_profile(self):
        from huldra_hardware import HardwareProfile, GPUInfo, save_hardware_profile, load_hardware_profile
        hw = HardwareProfile(
            gpu=GPUInfo(name="Test GPU", vram_total_gb=8.0),
            ram_total_gb=16.0,
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "hw.json"
            save_hardware_profile(hw, path)
            loaded = load_hardware_profile(path)
            assert loaded is not None
            assert loaded.gpu.name == "Test GPU"
            assert loaded.ram_total_gb == 16.0

    def test_load_nonexistent_returns_none(self):
        from huldra_hardware import load_hardware_profile
        assert load_hardware_profile(Path("/nonexistent/hw.json")) is None


# ============================================================================
# Recommender Tests
# ============================================================================

class TestRecommender:
    """Test profile recommendation logic."""

    def _make_hw(self, vram=8.0, ram=16.0, disk=100.0):
        """Helper to create a hardware profile with specific values."""
        from huldra_hardware import HardwareProfile, GPUInfo, StorageInfo
        return HardwareProfile(
            gpu=GPUInfo(vram_total_gb=vram, vendor="nvidia"),
            ram_total_gb=ram,
            ram_available_gb=ram * 0.75,
            storage=StorageInfo(path="C:\\", free_gb=disk),
            usable_vram_gb=max(0.0, vram - 0.5),
            usable_ram_gb=max(0.0, ram * 0.75 - 2.0),
            usable_disk_gb=max(0.0, disk - 5.0),
        )

    def test_recommend_profiles_returns_results(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        assert len(results) == 4  # 3 primary + 1 optional worker

    def test_recommend_profiles_sorted_by_fit(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles, FitLevel
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        fits = [r.fit for r in results]
        # FULL should come before PARTIAL
        full_indices = [i for i, f in enumerate(fits) if f == FitLevel.FULL]
        partial_indices = [i for i, f in enumerate(fits) if f == FitLevel.PARTIAL]
        if full_indices and partial_indices:
            assert max(full_indices) < min(partial_indices)

    def test_low_vram_insufficient(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles, FitLevel
        # 2 GB VRAM — below all profile minimums
        hw = self._make_hw(vram=2.0, ram=16.0, disk=100.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        # All should be insufficient
        for r in results:
            assert r.fit == FitLevel.INSUFFICIENT

    def test_8gb_vram_16gb_ram_minimal_tier(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles, FitLevel
        # Minimum viable: ~8 GB VRAM / ~16 GB RAM
        hw = self._make_hw(vram=8.0, ram=16.0, disk=50.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        # At least one profile should fit (Gemma 4 E4B is smallest)
        fits = [r.fit for r in results]
        assert FitLevel.FULL in fits or FitLevel.PARTIAL in fits

    def test_gemma4_fits_minimal_hardware(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import check_requirements, FitLevel
        # 5 GB VRAM -> usable 4.5 GB >= Gemma min 4.0
        # 16 GB RAM -> available 12.0 -> usable 10.0 GB >= Gemma min 8.0
        hw = self._make_hw(vram=5.0, ram=16.0, disk=15.0)
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        fit, checks, reasons = check_requirements(hw, p)
        assert fit in (FitLevel.FULL, FitLevel.PARTIAL)

    def test_manual_override_insufficient_profile(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles, FitLevel
        hw = self._make_hw(vram=2.0, ram=8.0, disk=50.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog, manual_override="qwen38-27b")
        # The override should be first
        assert results[0].profile.id == "qwen38-27b"
        assert results[0].fit == FitLevel.INSUFFICIENT
        # Should have a manual override warning
        assert any("MANUAL OVERRIDE" in r for r in results[0].reasons)

    def test_manual_override_unknown_profile_ignored(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles
        hw = self._make_hw(vram=8.0, ram=16.0, disk=100.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog, manual_override="nonexistent")
        # Should not crash, unknown profile just logged as warning
        assert len(results) == 4  # 3 primary + 1 optional worker

    def test_check_requirements_all_met(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import check_requirements, FitLevel
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        fit, checks, reasons = check_requirements(hw, p)
        assert fit == FitLevel.FULL
        assert all(c.meets for c in checks)

    def test_check_requirements_vram_insufficient(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import check_requirements, FitLevel
        hw = self._make_hw(vram=2.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen36-35b-apex")
        fit, checks, reasons = check_requirements(hw, p)
        assert fit == FitLevel.INSUFFICIENT
        vram_check = [c for c in checks if c.resource == "vram"][0]
        assert not vram_check.meets

    def test_check_requirements_ram_insufficient(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import check_requirements, FitLevel
        hw = self._make_hw(vram=12.0, ram=4.0, disk=200.0)
        catalog = create_v1_default_catalog()
        p = catalog.get("qwen36-35b-apex")
        fit, checks, reasons = check_requirements(hw, p)
        assert fit == FitLevel.INSUFFICIENT
        ram_check = [c for c in checks if c.resource == "ram"][0]
        assert not ram_check.meets

    def test_recommendation_report_format(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles, format_recommendation_report
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        report = format_recommendation_report(hw, results)
        assert "=== Huldra V1 Profile Recommendation ===" in report
        assert "GPU:" in report
        assert "RAM:" in report
        assert "Profiles:" in report

    def test_get_best_profile(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import get_best_profile
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        best = get_best_profile(hw, catalog)
        assert best is not None
        assert best.is_usable

    def test_get_best_profile_none_usable(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import get_best_profile
        hw = self._make_hw(vram=0.0, ram=2.0, disk=1.0)
        catalog = create_v1_default_catalog()
        best = get_best_profile(hw, catalog)
        # Even with no fit, should return something
        assert best is not None

    def test_recommendation_is_usable_property(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles, FitLevel
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        for r in results:
            if r.fit in (FitLevel.FULL, FitLevel.PARTIAL):
                assert r.is_usable
            elif r.fit == FitLevel.INSUFFICIENT:
                assert not r.is_usable

    def test_recommendation_to_dict(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import recommend_profiles
        hw = self._make_hw(vram=12.0, ram=24.0, disk=200.0)
        catalog = create_v1_default_catalog()
        results = recommend_profiles(hw, catalog)
        for r in results:
            d = r.to_dict()
            assert "profile_id" in d
            assert "fit" in d
            assert "checks" in d
            assert "reasons" in d

    def test_recommendation_margin_calculation(self):
        from huldra_profiles import create_v1_default_catalog
        from huldra_recommender import check_requirements
        hw = self._make_hw(vram=10.0, ram=16.0, disk=50.0)
        catalog = create_v1_default_catalog()
        p = catalog.get("gemma4-e4b")
        fit, checks, reasons = check_requirements(hw, p)
        vram_check = [c for c in checks if c.resource == "vram"][0]
        assert vram_check.margin_gb > 0
        assert vram_check.meets
