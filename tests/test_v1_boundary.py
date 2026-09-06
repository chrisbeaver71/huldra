"""
Adapter Boundary and Profile Integration Tests for Huldra V1.

Proves that:
1. The adapter/facade boundary is present (Huldra modules are additive)
2. The facade can be imported and initialized
3. Profile catalog loads correctly with exactly 3 primary profiles
4. Hardware detection returns valid results
5. Recommender produces valid output
6. All Huldra adapter modules import cleanly
7. The facade orchestrates the full first-run path
8. Manual profile override works
9. Asset verification works
10. Backend config resolution works
11. State and memory operations work through the facade

Run: python -m pytest tests/test_v1_boundary.py -v
"""
import os
import pathlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure source/ is on the path for imports
_HERE = pathlib.Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "source"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))


# ============================================================================
# Adapter Boundary: All Huldra modules import cleanly
# ============================================================================

class TestUpstreamTracking:
    """Verify upstream remote is configured and tracked correctly."""

    def test_upstream_remote_exists(self):
        """The upstream remote should be configured."""
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "upstream"],
            capture_output=True, text=True,
            cwd=str(_HERE.parent),
        )
        assert result.returncode == 0, "upstream remote not configured"
        assert "NousResearch/hermes-agent" in result.stdout

    def test_origin_remote_is_huldra(self):
        """The origin remote should point to the Huldra publication repo."""
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True,
            cwd=str(_HERE.parent),
        )
        assert result.returncode == 0
        assert "chrisbeaver71/huldra" in result.stdout


# ============================================================================
# Adapter Boundary: All Huldra modules import cleanly
# ============================================================================

    def test_import_huldra_facade(self):
        import huldra_facade
        assert hasattr(huldra_facade, "HuldraFacade")

    def test_import_huldra_profiles(self):
        import huldra_profiles
        assert hasattr(huldra_profiles, "ProfileCatalog")
        assert hasattr(huldra_profiles, "create_v1_default_catalog")

    def test_import_huldra_hardware(self):
        import huldra_hardware
        assert hasattr(huldra_hardware, "detect_hardware")
        assert hasattr(huldra_hardware, "HardwareProfile")

    def test_import_huldra_recommender(self):
        import huldra_recommender
        assert hasattr(huldra_recommender, "recommend_profiles")
        assert hasattr(huldra_recommender, "FitLevel")

    def test_import_huldra_chat(self):
        import huldra_chat
        assert hasattr(huldra_chat, "ChatSession")
        assert hasattr(huldra_chat, "Transcript")

    def test_import_huldra_tools(self):
        import huldra_tools
        assert hasattr(huldra_tools, "ToolRegistry")
        assert hasattr(huldra_tools, "register_v1_tools")

    def test_import_huldra_file_context(self):
        import huldra_file_context
        assert hasattr(huldra_file_context, "PathGuard")
        assert hasattr(huldra_file_context, "FileContext")

    def test_import_huldra_state(self):
        import huldra_state
        assert hasattr(huldra_state, "StateStore")
        assert hasattr(huldra_state, "MemoryStore")

    def test_import_huldra_status(self):
        import huldra_status
        assert hasattr(huldra_status, "StatusTracker")
        assert hasattr(huldra_status, "ComponentStatus")

    def test_import_huldra_routing(self):
        import huldra_routing
        assert hasattr(huldra_routing, "is_huldra_path")
        assert hasattr(huldra_routing, "is_latch_path")

    def test_upstream_backend_importable(self):
        """Upstream backend.py is still importable alongside Huldra modules."""
        from backend import BackendConfig, LocalModelBackend, BackendStatus
        assert BackendConfig is not None
        assert LocalModelBackend is not None

    def test_upstream_hermes_constants_importable(self):
        """Upstream hermes_constants is still importable."""
        import hermes_constants
        assert hasattr(hermes_constants, "__file__")


# ============================================================================
# Profile Catalog: Exactly 3 primary profiles
# ============================================================================

class TestProfileCatalogBoundary:
    """Verify the catalog has exactly 3 primary + 1 optional worker profiles."""

    def test_default_catalog_has_4_profiles(self):
        """3 primary user-facing + 1 optional worker (Ling)."""
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        assert len(catalog.profiles) == 4

    def test_exactly_3_primary_profiles(self):
        """Exactly 3 primary user-facing profiles."""
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        primary = [p for p in catalog.profiles if p.role == "user-facing" and not p.optional]
        assert len(primary) == 3

    def test_primary_profile_ids_match_expected(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        primary = [p for p in catalog.profiles if p.role == "user-facing" and not p.optional]
        ids = set(p.id for p in primary)
        assert "qwen36-35b-apex" in ids
        assert "gemma4-e4b" in ids
        assert "qwen38-27b" in ids

    def test_ling_is_optional_worker(self):
        """Ling 3.0 Tiny must be optional worker, never primary."""
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        ling_profiles = [p for p in catalog.profiles if "ling" in p.id.lower()]
        assert len(ling_profiles) == 1, "Expected exactly one Ling profile"
        ling = ling_profiles[0]
        assert ling.role == "worker", f"Ling role should be 'worker', got '{ling.role}'"
        assert ling.optional is True, "Ling must be optional"

    def test_no_other_optional_profiles(self):
        """Only Ling should be optional in the default catalog."""
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        optional = [p for p in catalog.profiles if p.optional]
        assert len(optional) == 1
        assert "ling" in optional[0].id.lower()

    def test_catalog_validation_passes(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        errors = catalog.validate()
        assert errors == [], f"Catalog validation errors: {errors}"

    def test_catalog_roundtrip(self):
        from huldra_profiles import ProfileCatalog
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            catalog.save(path)
            loaded = ProfileCatalog.from_file(path)
            assert len(loaded.profiles) == 4
            assert loaded.version == catalog.version

    def test_each_profile_has_model_artifact(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        for p in catalog.profiles:
            assert p.model_artifact is not None, f"{p.id} missing model_artifact"
            assert p.model_artifact.name, f"{p.id} model_artifact has no name"

    def test_each_profile_has_runtime_config(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        for p in catalog.profiles:
            assert p.runtime.backend_type, f"{p.id} missing backend_type"
            assert p.runtime.context_length > 0, f"{p.id} has zero context_length"

    def test_each_profile_has_resource_requirements(self):
        from huldra_profiles import create_v1_default_catalog
        catalog = create_v1_default_catalog()
        for p in catalog.profiles:
            assert p.resources.min_ram_gb > 0, f"{p.id} has zero min_ram_gb"


# ============================================================================
# Facade initialization
# ============================================================================

class TestFacadeInitialization:
    """Verify the facade can be initialized and basic operations work."""

    def test_facade_init_default(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        assert facade.huldra_home is not None
        assert facade.huldra_home.is_dir()

    def test_facade_init_explicit_home(self, tmp_path):
        from huldra_facade import HuldraFacade
        # Create minimal structure
        (tmp_path / "config").mkdir()
        (tmp_path / "Models").mkdir()
        (tmp_path / "state").mkdir()
        (tmp_path / "evidence").mkdir()
        (tmp_path / ".hermes-live").mkdir()
        facade = HuldraFacade(huldra_home=tmp_path)
        assert facade.huldra_home == tmp_path

    def test_facade_catalog_loaded(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        assert len(facade.catalog.profiles) == 4  # 3 primary + 1 optional worker

    def test_facade_list_profiles(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        profiles = facade.list_profiles()
        assert len(profiles) == 4

    def test_facade_list_primary_profiles(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        primary = facade.list_primary_profiles()
        assert len(primary) == 3  # only user-facing, non-optional

    def test_facade_get_profile(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        p = facade.get_profile("qwen36-35b-apex")
        assert p is not None
        assert p.name == "Qwen 3.6 35B A3B (APEX I-Compact)"

    def test_facade_tool_registry(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        schemas = facade.get_tool_schemas()
        assert len(schemas) >= 5
        names = [s["function"]["name"] for s in schemas]
        assert "read_file" in names
        assert "terminal" in names


# ============================================================================
# First-run path
# ============================================================================

class TestFirstRunPath:
    """Verify the first-run detect → recommend path works."""

    def test_first_run_returns_result(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        result = facade.first_run(use_hw_cache=False)
        assert result.hardware is not None
        assert len(result.recommendations) == 4  # 4 profiles total
        assert result.report != ""

    def test_first_run_persists_active_profile(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        result = facade.first_run(use_hw_cache=False)
        if result.best_profile:
            active = facade.state.get("session.active_profile")
            assert active == result.best_profile.profile.id

    def test_first_run_with_manual_override(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        result = facade.first_run(manual_override="gemma4-e4b", use_hw_cache=False)
        # With manual override, gemma4-e4b should be first in recommendations
        assert result.recommendations[0].profile.id == "gemma4-e4b"
        # best_profile may be the override or the auto-best depending on fit
        assert result.best_profile is not None


# ============================================================================
# Asset verification
# ============================================================================

class TestAssetVerification:
    """Verify asset verification works through the facade."""

    def test_verify_assets_returns_list(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        facade.first_run(use_hw_cache=False)
        assets = facade.verify_assets()
        assert isinstance(assets, list)

    def test_verify_assets_for_specific_profile(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        assets = facade.verify_assets("qwen36-35b-apex")
        assert len(assets) >= 2  # model + runtime at minimum


# ============================================================================
# Backend resolution
# ============================================================================

class TestBackendResolution:
    """Verify backend config resolution works through the facade."""

    def test_resolve_backend_returns_config(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        facade.first_run(use_hw_cache=False)
        config = facade.resolve_backend()
        # config may be None if no active profile, but should not raise
        if config:
            from backend import BackendConfig
            assert isinstance(config, BackendConfig)

    def test_resolve_backend_for_profile(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        config = facade.resolve_backend("qwen36-35b-apex")
        if config:
            assert config.name == "qwen36-35b-apex"
            assert "8080" in config.base_url or "808" in config.base_url


# ============================================================================
# Manual profile selection
# ============================================================================

class TestManualSelection:
    """Verify manual profile override works through the facade."""

    def test_select_profile(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        facade.detect_hardware(use_cache=False)
        rec = facade.select_profile("gemma4-e4b")
        assert rec.profile.id == "gemma4-e4b"
        assert facade.state.get("session.active_profile") == "gemma4-e4b"

    def test_select_nonexistent_profile_raises(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        with pytest.raises(ValueError, match="not found"):
            facade.select_profile("nonexistent-profile")


# ============================================================================
# State and memory through facade
# ============================================================================

class TestStateAndMemoryFacade:
    """Verify state and memory operations work through the facade."""

    def test_set_get_preference(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        facade.set_preference("theme", "dark")
        assert facade.get_preference("theme") == "dark"

    def test_remember_recall(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        facade.remember("test_key", "test content", tags=["test"])
        assert facade.recall("test_key") == "test content"


# ============================================================================
# Status through facade
# ============================================================================

class TestStatusFacade:
    """Verify status reporting works through the facade."""

    def test_get_status(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        status = facade.get_status()
        assert "huldra" in status
        assert "components" in status
        assert status["huldra"]["catalog_profiles"] == 4  # 3 primary + 1 optional worker

    def test_health_check(self):
        from huldra_facade import HuldraFacade
        facade = HuldraFacade()
        health = facade.health_check()
        assert "catalog" in health
        assert health["catalog"] == "healthy"
