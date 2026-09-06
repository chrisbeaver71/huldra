"""Path and Slack channel guards for Huldra-native Hermes prep.

This module intentionally rejects Project LATCH workspaces and the #latch
channel so a future Huldra cutover cannot silently inherit LATCH defaults.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

HULDRA_ROOT = Path(r"E:\Huldra")

ALLOWED_ROOTS = (
    HULDRA_ROOT,
    HULDRA_ROOT / "Results",
    HULDRA_ROOT / "docs",
    HULDRA_ROOT / "ahk",
    HULDRA_ROOT / "runtimes",
    HULDRA_ROOT / "evidence",
    HULDRA_ROOT / ".hermes-live",
    HULDRA_ROOT / "boards" / "huldra",
    HULDRA_ROOT / "ops" / "hermes",
)

FORBIDDEN_ROOTS = (
    Path(r"<LEGACY_WORKSPACE>"),
    Path(r"<LEGACY_DRIVE_PATH>"),
)

HULDRA_CHANNEL_ID = "C0BKR5LEYV8"
HULDRA_CHANNEL_NAME = "huldra"
LATCH_CHANNEL_ID = "C0BKT3BEP4H"
LATCH_CHANNEL_NAME = "latch"

PathLike = Union[str, Path]


def _norm_path(path: PathLike) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _norm_channel(channel_id_or_name: str) -> str:
    s = (channel_id_or_name or "").strip()
    if s.startswith("#"):
        s = s[1:]
    # thread/group ids look like C0BKR5LEYV8:timestamp — use base id
    if ":" in s and s.upper().startswith("C"):
        s = s.split(":", 1)[0]
    return s.lower()


def is_latch_path(path: PathLike) -> bool:
    """Return True if path is under a forbidden Project LATCH root."""
    try:
        p = _norm_path(path)
    except Exception:
        raw = str(path).replace("/", "\\").lower()
        return "project latch" in raw
    raw = str(p).replace("/", "\\").lower()
    if "project latch" in raw:
        return True
    for forbidden in FORBIDDEN_ROOTS:
        try:
            fr = forbidden.resolve(strict=False)
            if p == fr or fr in p.parents or p in fr.parents:
                pass
        except Exception:
            pass
        fraw = str(forbidden).replace("/", "\\").lower()
        if raw == fraw or raw.startswith(fraw.rstrip("\\") + "\\"):
            return True
    return False


def is_huldra_path(path: PathLike) -> bool:
    """Return True if path is under E:\\Huldra and not a LATCH root."""
    if is_latch_path(path):
        return False
    try:
        p = _norm_path(path)
    except Exception:
        raw = str(path).replace("/", "\\").lower()
        return raw.startswith(r"e:\huldra")
    raw = str(p).replace("/", "\\").lower()
    huldra = str(HULDRA_ROOT.resolve(strict=False)).replace("/", "\\").lower()
    if raw == huldra or raw.startswith(huldra.rstrip("\\") + "\\"):
        return True
    return str(path).replace("/", "\\").lower().startswith(r"e:\huldra")


def is_latch_channel(channel_id_or_name: str) -> bool:
    """Return True if channel refers to #latch / C0BKT3BEP4H."""
    c = _norm_channel(channel_id_or_name)
    return c in {LATCH_CHANNEL_ID.lower(), LATCH_CHANNEL_NAME.lower()}


def is_huldra_channel(channel_id_or_name: str) -> bool:
    c = _norm_channel(channel_id_or_name)
    return c in {HULDRA_CHANNEL_ID.lower(), HULDRA_CHANNEL_NAME.lower()}


def assert_huldra_path(path: PathLike) -> Path:
    """Allow only paths under E:\\Huldra; reject LATCH roots with a clear error."""
    if is_latch_path(path):
        raise PermissionError(
            f"LATCH path forbidden for Huldra Hermes: {path!s}. "
            f"Huldra product defaults use paths under {HULDRA_ROOT} only "
            f"(not Project LATCH / profiles/latch). "
            f"Fix cwd or config to E:\\Huldra."
        )
    p = _norm_path(path)
    if is_huldra_path(path):
        return p
    raise PermissionError(
        f"Path not under Huldra root {HULDRA_ROOT}: {path!s}. "
        f"Expected E:\\Huldra\\... (boards under E:\\Huldra\\boards\\huldra)."
    )


def assert_huldra_channel(channel_id_or_name: str) -> str:
    """Allow #huldra / C0BKR5LEYV8; reject #latch / C0BKT3BEP4H."""
    if is_latch_channel(channel_id_or_name):
        raise PermissionError(
            f"LATCH channel forbidden for Huldra Hermes: {channel_id_or_name!s}. "
            f"Use #{HULDRA_CHANNEL_NAME} / {HULDRA_CHANNEL_ID} "
            f"(do not default to #latch)."
        )
    if not is_huldra_channel(channel_id_or_name):
        raise PermissionError(
            f"Channel not allowed for Huldra coordination: {channel_id_or_name!s}. "
            f"Allowed: #{HULDRA_CHANNEL_NAME} / {HULDRA_CHANNEL_ID}."
        )
    return _norm_channel(channel_id_or_name)
