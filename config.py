"""
artixinstall.lib.config
~~~~~~~~~~~~~~~~~~~~~~~~

ArtixConfig
    Extends upstream ArchConfig with Artix-specific fields.
    The most important addition is ``init_type`` – the user's chosen
    init system.

ArtixConfigHandler
    Thin wrapper that builds an ArtixConfig from CLI args and/or a JSON
    config file.  Compatible with the upstream ArchConfigHandler interface
    so that guided.py can call it unchanged (mostly).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import logging as _logging
_log = _logging.getLogger("artixinstall.config")
debug = _log.debug; info = _log.info; warn = _log.warning; error = _log.error

from artixinstall.lib.init import InitType


@dataclass
class ArtixConfig:
    """
    Extends the logical installation configuration with Artix fields.

    We do NOT subclass ArchConfig here to avoid fragile MRO coupling.
    Instead we wrap it: the guided script instantiates ArtixConfig and
    reads/writes both configs together.
    """

    # ── Init system selection ────────────────────────────────────────────
    init_type: InitType = InitType.OpenRC

    # ── Artix-specific package overrides ─────────────────────────────────
    include_arch_compat_repos: bool = False
    """
    When True, add (commented-out) Arch [extra]/[community] repos to
    pacman.conf.  The user must manually uncomment them to use Arch packages
    that aren't yet in Artix repos.  Disabled by default to avoid accidental
    systemd contamination.
    """

    include_lib32: bool = False
    """Enable [lib32] for 32-bit application support (Steam, Wine, etc.)."""

    # ── Mirror configuration ──────────────────────────────────────────────
    artix_mirrors: list[str] = field(default_factory=list)
    """
    Custom Artix mirror URLs.  If empty, artixinstall uses its built-in
    default mirror list.
    """

    # ── Time sync ────────────────────────────────────────────────────────
    time_sync_override: Optional[str] = None
    """
    Override the default NTP daemon for the selected init.
    If None, the init backend's default is used.
    Accepted values: 'openntpd', 'ntp', 'chrony'.
    """

    def json(self) -> dict:
        return {
            "init_type":                self.init_type.value,
            "include_arch_compat_repos": self.include_arch_compat_repos,
            "include_lib32":            self.include_lib32,
            "artix_mirrors":            self.artix_mirrors,
            "time_sync_override":       self.time_sync_override,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ArtixConfig":
        init_str = data.get("init_type", "openrc")
        try:
            init_type = InitType(init_str)
        except ValueError:
            warn(f"Unknown init_type '{init_str}', defaulting to openrc")
            init_type = InitType.OpenRC

        return cls(
            init_type=init_type,
            include_arch_compat_repos=data.get("include_arch_compat_repos", False),
            include_lib32=data.get("include_lib32", False),
            artix_mirrors=data.get("artix_mirrors", []),
            time_sync_override=data.get("time_sync_override"),
        )

    @classmethod
    def from_file(cls, path: Path) -> "ArtixConfig":
        try:
            data = json.loads(path.read_text())
            return cls.from_json(data)
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            error(f"Could not load Artix config from {path}: {exc}")
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.json(), indent=2))
        info(f"Artix config saved to {path}")
