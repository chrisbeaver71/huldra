"""Huldra V1 Bounded File/Desktop Context.

Provides:
- Explicit allowlists for file access paths
- Path normalization and validation
- Refusal behavior for out-of-scope access
- Desktop context boundaries (safe, useful subset)
- No ambient filesystem access

All file operations go through this module's path guard before execution.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Optional


class FileAccessError(Exception):
    """Raised when a file operation is denied by the path guard."""
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Access denied for {path}: {reason}")


class PathGuard:
    """Enforces explicit allowlists for file access.

    By default, only the Huldra project tree and its designated
    external state directories are accessible. All other paths are
    refused unless explicitly added to the allowlist.

    Usage:
        guard = PathGuard(
            allowed_roots=["E:/Huldra", "E:/Huldra/boards/huldra"],
            denied_patterns=["*.env", "*.db", "*.sqlite"],
        )
        guard.validate("E:/Huldra/ops/hermes/backend.py")  # OK
        guard.validate("C:/Users/generic/.env")  # FileAccessError
    """

    def __init__(
        self,
        allowed_roots: Optional[list[str]] = None,
        denied_patterns: Optional[list[str]] = None,
        huldra_root: str = "E:/Huldra",
    ):
        self._huldra_root = Path(huldra_root)
        self._allowed_roots: list[Path] = []
        self._denied_patterns: list[str] = denied_patterns or [
            "*.env",
            "*.db",
            "*.sqlite",
            "*.sqlite3",
            "*.key",
            "*.pem",
            "*.p12",
            "*.pfx",
        ]

        if allowed_roots:
            for root in allowed_roots:
                self._allowed_roots.append(Path(root))
        else:
            # Default: Huldra tree + designated state directories
            self._allowed_roots = [
                self._huldra_root,
            ]

    def add_allowed_root(self, path: str) -> None:
        """Add a path to the allowlist."""
        p = Path(path)
        if p not in self._allowed_roots:
            self._allowed_roots.append(p)

    def remove_allowed_root(self, path: str) -> None:
        """Remove a path from the allowlist."""
        p = Path(path)
        self._allowed_roots = [r for r in self._allowed_roots if r != p]

    @property
    def allowed_roots(self) -> list[str]:
        return [str(r) for r in self._allowed_roots]

    def is_allowed(self, path: str) -> bool:
        """Check if a path is within any allowed root (without raising)."""
        try:
            self.validate(path)
            return True
        except FileAccessError:
            return False

    def validate(self, path: str) -> Path:
        """Validate a path against the allowlist and deny patterns.

        Returns the resolved Path if allowed.
        Raises FileAccessError if denied.
        """
        p = Path(path).resolve()

        # Check deny patterns first
        name = p.name
        for pattern in self._denied_patterns:
            if self._matches_pattern(name, pattern):
                raise FileAccessError(
                    path,
                    f"File matches denied pattern: {pattern}",
                )

        # Check against allowed roots
        for root in self._allowed_roots:
            root_resolved = root.resolve()
            try:
                p.relative_to(root_resolved)
                return p
            except ValueError:
                continue

        raise FileAccessError(
            path,
            f"Path is outside all allowed roots: {[str(r) for r in self._allowed_roots]}",
        )

    def validate_directory(self, path: str) -> Path:
        """Validate a directory path. Same as validate() but for directories."""
        return self.validate(path)

    def list_allowed(self) -> list[str]:
        """List all paths under allowed roots (one level, non-recursive)."""
        result = []
        for root in self._allowed_roots:
            if root.is_dir():
                for entry in sorted(root.iterdir()):
                    result.append(str(entry))
        return result

    @staticmethod
    def _matches_pattern(name: str, pattern: str) -> bool:
        """Simple glob-like pattern matching for deny patterns."""
        if pattern.startswith("*"):
            suffix = pattern[1:]
            return name.endswith(suffix)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return name.startswith(prefix)
        return name == pattern


class FileContext:
    """Provides bounded file operations through a PathGuard.

    All file operations (read, write, search) are routed through
    this module to enforce the path allowlist.
    """

    def __init__(self, guard: Optional[PathGuard] = None):
        self._guard = guard or PathGuard()

    @property
    def guard(self) -> PathGuard:
        return self._guard

    def read_file(self, path: str) -> str:
        """Read a file, validating path access first."""
        resolved = self._guard.validate(path)
        return resolved.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        """Write a file, validating path access first."""
        resolved = self._guard.validate(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

    def file_exists(self, path: str) -> bool:
        """Check if a file exists and is within allowed roots."""
        try:
            resolved = self._guard.validate(path)
            return resolved.exists()
        except FileAccessError:
            return False

    def search_files(
        self,
        pattern: str,
        search_path: Optional[str] = None,
    ) -> list[str]:
        """Search for files matching a glob pattern within allowed roots."""
        if search_path:
            root = self._guard.validate(search_path)
        else:
            root = self._guard.allowed_roots[0] if self._guard.allowed_roots else Path.cwd()

        results = []
        try:
            for p in root.rglob(pattern):
                if p.is_file():
                    results.append(str(p))
        except PermissionError:
            pass
        return results

    def get_desktop_context(self) -> dict[str, str]:
        """Get safe desktop context: current working directory, username,
        platform info. No ambient filesystem access."""
        return {
            "cwd": os.getcwd(),
            "platform": os.name,
            "home": str(Path.home()),
            "huldra_root": str(self._guard._huldra_root),
        }
