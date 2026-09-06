"""Guards: Huldra paths/channels allowed; LATCH rejected."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_OPS = _HERE.parent
_SOURCE = _OPS / "source"
_STAGING_FALLBACK = Path(r"E:\Huldra\huldra-hermes-prep")
for p in (_SOURCE, _OPS, _STAGING_FALLBACK):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from huldra_prep.huldra_routing import (
    HULDRA_CHANNEL_ID,
    HULDRA_ROOT,
    assert_huldra_channel,
    assert_huldra_path,
    is_huldra_path,
    is_latch_channel,
    is_latch_path,
)


def test_huldra_root_allowed():
    p = assert_huldra_path(HULDRA_ROOT)
    assert "huldra" in str(p).lower()


def test_huldra_subpaths_allowed():
    for sub in ("Results", "docs", "ahk", "runtimes", ".hermes-live", "evidence", "boards"):
        assert_huldra_path(HULDRA_ROOT / sub)


def test_latch_paths_rejected():
    for bad in (
        r"C:\Users\generic\project Latch",
        r"C:\Users\generic\project Latch\HERMES.md",
        r"G:\My Drive\project Latch",
        r"G:\My Drive\project Latch\results",
    ):
        assert is_latch_path(bad)
        assert not is_huldra_path(bad)
        with pytest.raises(PermissionError, match="LATCH"):
            assert_huldra_path(bad)


def test_non_huldra_path_rejected():
    with pytest.raises(PermissionError):
        assert_huldra_path(r"C:\Users\generic\AppData\Local\hermes")


def test_huldra_channel_allowed():
    assert assert_huldra_channel("#huldra") == "huldra"
    assert assert_huldra_channel(HULDRA_CHANNEL_ID) == HULDRA_CHANNEL_ID.lower()
    assert assert_huldra_channel(f"{HULDRA_CHANNEL_ID}:1788674767.294709") == HULDRA_CHANNEL_ID.lower()


def test_latch_channel_rejected():
    for bad in ("#latch", "latch", "C0BKT3BEP4H", "C0BKT3BEP4H:1787218134.883429"):
        assert is_latch_channel(bad)
        with pytest.raises(PermissionError, match="LATCH"):
            assert_huldra_channel(bad)


def test_other_channel_rejected():
    with pytest.raises(PermissionError):
        assert_huldra_channel("#shann-home")


def test_is_huldra_path_helpers():
    assert is_huldra_path(r"E:\Huldra")
    assert is_huldra_path(r"E:\Huldra\boards\huldra")
    assert not is_huldra_path(r"C:\Users\generic\project Latch")
    assert not is_huldra_path(r"G:\My Drive\project Latch")
