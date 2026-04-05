"""
artixinstall.lib.init.base
~~~~~~~~~~~~~~~~~~~~~~~~~~

Abstract base class every init backend must implement.
No concrete init knowledge lives here – only the contract.
"""

from __future__ import annotations

import subprocess
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Sequence


class ServiceAction(Enum):
    ENABLE  = auto()
    DISABLE = auto()
    START   = auto()
    STOP    = auto()


@dataclass
class ServiceResult:
    service:  str
    action:   ServiceAction
    success:  bool
    message:  str = ""


class InitBackend(ABC):
    """
    Abstract base class for all init-system backends.

    Parameters
    ----------
    target:
        Path to the chroot / install root (e.g. ``Path('/mnt')``).
    """

    def __init__(self, target: Path) -> None:
        self.target = target

    # ── Mandatory interface ────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable init name, e.g. 'OpenRC'."""

    @property
    @abstractmethod
    def base_packages(self) -> list[str]:
        """Packages required for this init to function."""

    @property
    @abstractmethod
    def time_sync_service(self) -> str:
        """Logical service name for NTP/time synchronisation."""

    @property
    @abstractmethod
    def time_sync_packages(self) -> list[str]:
        """Packages to install for time synchronisation."""

    @abstractmethod
    def enable_service(self, service: str, runlevel: str = "default") -> ServiceResult:
        """Enable *service* to start at boot."""

    @abstractmethod
    def disable_service(self, service: str) -> ServiceResult:
        """Prevent *service* from starting at boot."""

    @abstractmethod
    def configure_networking(self, use_nm: bool = True) -> list[str]:
        """Return packages for network management and perform init-specific setup."""

    @abstractmethod
    def configure_time_sync(self) -> list[str]:
        """Install and enable the time-sync daemon; return packages."""

    @abstractmethod
    def configure_display_manager(self, dm_service: str) -> ServiceResult:
        """Enable *dm_service* as the display manager."""

    @abstractmethod
    def set_default_target(self, graphical: bool = False) -> None:
        """Set the system default runlevel/target."""

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _clean_name(self, service: str) -> str:
        """Strip systemd-style unit suffixes (.service, .timer, etc.)."""
        for suffix in (".service", ".timer", ".socket", ".target"):
            if service.endswith(suffix):
                return service[: -len(suffix)]
        return service

    def _run(
        self, cmd: str | Sequence[str], *, check: bool = False
    ) -> subprocess.CompletedProcess:
        """Run *cmd* on the host system (outside the chroot)."""
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        return subprocess.run(list(cmd), capture_output=True, text=True, check=check)

    def _chroot(
        self, cmd: str | Sequence[str], *, check: bool = False
    ) -> subprocess.CompletedProcess:
        """Run *cmd* inside the install chroot via ``arch-chroot``."""
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        full = ["arch-chroot", str(self.target)] + list(cmd)
        return subprocess.run(full, capture_output=True, text=True, check=check)

    def _result(
        self,
        service: str,
        action: ServiceAction,
        proc: subprocess.CompletedProcess,
    ) -> ServiceResult:
        success = proc.returncode == 0
        msg = proc.stdout.strip() or proc.stderr.strip()
        return ServiceResult(service=service, action=action, success=success, message=msg)

    def enable_services(self, services: str | list[str]) -> list[ServiceResult]:
        """Batch-enable services; returns one result per service."""
        if isinstance(services, str):
            services = [services]
        return [self.enable_service(s) for s in services]

    def disable_services(self, services: str | list[str]) -> list[ServiceResult]:
        if isinstance(services, str):
            services = [services]
        return [self.disable_service(s) for s in services]
