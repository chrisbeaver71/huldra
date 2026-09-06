"""
Minimal V1 smoke test for Huldra Hermes.

Validates that:
1. The source tree structure is correct
2. Core modules can be imported
3. No LATCH coupling in shipped config/examples (as defaults)
4. Routing guards reject LATCH paths

Run: python -m pytest tests/test_v1_smoke.py -v
"""
import os
import pathlib
import sys

import pytest

# Ensure source/ is on the path for imports
_HERE = pathlib.Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "source"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))


class TestLayoutContract:
    """Verify the permanent tree layout is populated correctly."""

    def test_source_dir_exists(self):
        assert _SOURCE.is_dir(), f"source/ not found at {_SOURCE}"

    def test_core_dirs_present(self):
        for name in ("agent", "gateway", "tools", "hermes_cli", "plugins", "skills", "providers", "cron"):
            d = _SOURCE / name
            assert d.is_dir(), f"source/{name}/ missing"

    def test_config_dir_populated(self):
        config_dir = _HERE.parent / "config"
        assert config_dir.is_dir()
        assert (config_dir / "config.example.yaml").is_file(), "config.example.yaml missing"

    def test_scripts_dir_has_launch(self):
        scripts_dir = _HERE.parent / "scripts"
        assert scripts_dir.is_dir()
        assert (scripts_dir / "launch.cmd").is_file(), "launch.cmd missing"

    def test_docs_dir_has_required(self):
        docs_dir = _HERE.parent / "docs"
        assert docs_dir.is_dir()
        for name in ("architecture.md", "rollback.md", "LATCH_BAGGAGE_QUARANTINE.md"):
            assert (docs_dir / name).is_file(), f"docs/{name} missing"

    def test_readme_exists(self):
        readme = _HERE.parent / "README.md"
        assert readme.is_file(), "README.md missing"
        text = readme.read_text(encoding="utf-8")
        assert "Huldra" in text, "README should mention Huldra"
        assert "Nous Research" in text or "MIT" in text, "README should mention attribution"


class TestImportGuards:
    """Verify core modules can be imported from source/."""

    def test_import_hermes_constants(self):
        import hermes_constants
        assert hasattr(hermes_constants, "__file__")

    def test_import_hermes_logging(self):
        import hermes_logging
        assert hasattr(hermes_logging, "__file__")

    def test_import_utils(self):
        import utils
        assert hasattr(utils, "__file__")

    def test_import_huldra_routing(self):
        import huldra_routing
        assert hasattr(huldra_routing, "__file__")


class TestNoLatchCoupling:
    """Verify shipped config/examples do not use LATCH as an active default.

    Quarantine warnings that say "Do NOT use #latch" or "Do NOT route to
    project Latch" are correct guard-rails, not coupling.  The tests check
    that LATCH is not used as an *active default* in key config values.
    """

    def _read_text(self, relpath):
        p = _HERE.parent / relpath
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
        return ""

    def test_config_cwd_not_latch(self):
        """terminal.cwd must not point to a LATCH path."""
        text = self._read_text("config/config.example.yaml")
        # Find the cwd line under terminal:
        import re
        match = re.search(r'cwd:\s*(.+)', text)
        if match:
            cwd = match.group(1).strip()
            assert "project Latch" not in cwd, f"terminal.cwd is LATCH: {cwd}"
            assert "G:/My Drive" not in cwd, f"terminal.cwd is LATCH Drive: {cwd}"
        else:
            pytest.skip("terminal.cwd not found in config")

    def test_config_channel_not_latch(self):
        """Slack channel must not default to #latch."""
        text = self._read_text("config/config.example.yaml")
        # Check that #latch / C0BKT3BEP4H is not used as an active channel value
        import re
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "C0BKT3BEP4H" in stripped and (":" in stripped or "=" in stripped):
                # Check it's not inside a quarantine warning string
                if "Do not" not in stripped and "do not" not in stripped:
                    pytest.fail(f"Channel set to LATCH: {stripped}")

    def test_env_example_no_real_secrets(self):
        """The .env.example must have placeholders, not real API keys."""
        text = self._read_text("config/.env.example")
        if not text:
            pytest.skip(".env.example not found")
        import re
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not stripped:
                continue
            # Match: VAR_NAME=<20+ alphanumeric> (uncommented, real key pattern)
            if re.match(r'^[A-Z_]+\s*=\s*[a-zA-Z0-9_-]{20,}$', stripped):
                pytest.fail(f"Possible real secret in .env.example: {stripped[:40]}...")

    def test_readme_no_latch_active_default(self):
        """README.md must not present LATCH as the active operating default."""
        text = self._read_text("README.md")
        for line in text.splitlines():
            lower = line.lower()
            if "#latch" in lower:
                # OK if it's a quarantine/warning context
                if any(kw in lower for kw in ("do not", "quarantine", "forbidden", "removed", "not")):
                    continue
                pytest.fail(f"README.md references #latch as active default: {line.strip()}")


class TestRoutingGuards:
    """Verify the Huldra routing guards work."""

    def test_reject_latch_path(self):
        import huldra_routing
        if hasattr(huldra_routing, "is_huldra_path"):
            assert not huldra_routing.is_huldra_path("C:/Users/generic/project Latch")
            assert not huldra_routing.is_huldra_path("G:\\My Drive\\project Latch")

    def test_accept_huldra_path(self):
        import huldra_routing
        if hasattr(huldra_routing, "is_huldra_path"):
            assert huldra_routing.is_huldra_path("E:/Huldra")
            assert huldra_routing.is_huldra_path("E:\\Huldra")

    def test_reject_latch_channel(self):
        import huldra_routing
        if hasattr(huldra_routing, "is_huldra_channel"):
            assert not huldra_routing.is_huldra_channel("C0BKT3BEP4H")
            assert not huldra_routing.is_huldra_channel("#latch")

    def test_accept_huldra_channel(self):
        import huldra_routing
        if hasattr(huldra_routing, "is_huldra_channel"):
            assert huldra_routing.is_huldra_channel("C0BKR5LEYV8")
            assert huldra_routing.is_huldra_channel("#huldra")
