"""
artixinstall.lib.init.s6
~~~~~~~~~~~~~~~~~~~~~~~~~

s6 + s6-rc backend for artixinstall.

Service management
    Services source dirs live in /etc/s6/sv/ (installed by *-s6 packages).
    Enabling a service = creating a marker in the 'default' bundle's
    contents.d/ directory so s6-db-reload picks it up on next boot.

EXPERIMENTAL – s6 has the smallest Artix package coverage in MVP v1.
"""

from __future__ import annotations

from pathlib import Path

from .base import InitBackend, ServiceAction, ServiceResult


_S6_CONTENTS_D = "/etc/s6/adminsv/default/contents.d"


class S6Backend(InitBackend):
    """
    EXPERIMENTAL – s6 / s6-rc backend.

    Uses the Artix contents.d convention so services are compiled into
    the default bundle on first boot.
    """

    def __init__(self, target: Path) -> None:
        super().__init__(target)

    @property
    def name(self) -> str:
        return "s6"

    @property
    def base_packages(self) -> list[str]:
        return ["base", "s6", "s6-rc", "artix-s6-meta"]

    @property
    def time_sync_service(self) -> str:
        return "openntpd"

    @property
    def time_sync_packages(self) -> list[str]:
        return ["openntpd", "openntpd-s6"]

    def enable_service(self, service: str, runlevel: str = "default") -> ServiceResult:
        svc      = self._clean_name(service)
        marker   = f"{_S6_CONTENTS_D}/{svc}"
        cmd      = f"mkdir -p '{_S6_CONTENTS_D}' && touch '{marker}'"
        proc     = self._chroot(["sh", "-c", cmd])
        return self._result(svc, ServiceAction.ENABLE, proc)

    def disable_service(self, service: str) -> ServiceResult:
        svc  = self._clean_name(service)
        proc = self._chroot(["rm", "-f", f"{_S6_CONTENTS_D}/{svc}"])
        return self._result(svc, ServiceAction.DISABLE, proc)

    def configure_networking(self, use_nm: bool = True) -> list[str]:
        if use_nm:
            packages = ["networkmanager", "networkmanager-s6"]
            self.enable_service("NetworkManager")
        else:
            packages = ["dhcpcd", "dhcpcd-s6"]
            self.enable_service("dhcpcd")
        return packages

    def configure_time_sync(self) -> list[str]:
        self.enable_service(self.time_sync_service)
        return self.time_sync_packages

    def configure_display_manager(self, dm_service: str) -> ServiceResult:
        return self.enable_service(self._clean_name(dm_service))

    def set_default_target(self, graphical: bool = False) -> None:
        pass  # s6 uses bundles; DM in the default bundle is sufficient.

    def translate_package(self, base_name: str) -> str:
        _s6_variants = {
            "networkmanager": "networkmanager-s6",
            "dhcpcd":         "dhcpcd-s6",
            "sshd":           "openssh-s6",
            "cronie":         "cronie-s6",
            "sddm":           "sddm-s6",
            "gdm":            "gdm-s6",
            "lightdm":        "lightdm-s6",
            "cups":           "cups-s6",
            "bluetooth":      "bluez-s6",
            "ufw":            "ufw-s6",
            "openntpd":       "openntpd-s6",
        }
        return _s6_variants.get(base_name.lower(), base_name)
