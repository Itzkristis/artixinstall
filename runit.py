"""artixinstall.lib.init.runit – runit backend."""
from __future__ import annotations
from pathlib import Path
from .base import InitBackend, ServiceAction, ServiceResult

_SV_DIR      = "/etc/runit/sv"
_CURRENT_DIR = "/etc/runit/runsvdir/current"


class RunitBackend(InitBackend):
    """runit backend: symlink /etc/runit/sv/<n> → /etc/runit/runsvdir/current/<n>."""

    def __init__(self, target: Path) -> None:
        super().__init__(target)

    @property
    def name(self) -> str:
        return "runit"

    @property
    def base_packages(self) -> list[str]:
        return ["base", "runit", "artix-runit-meta"]

    @property
    def time_sync_service(self) -> str:
        return "openntpd"

    @property
    def time_sync_packages(self) -> list[str]:
        return ["openntpd", "openntpd-runit"]

    def enable_service(self, service: str, runlevel: str = "default") -> ServiceResult:
        svc  = self._clean_name(service)
        sv   = f"{_SV_DIR}/{svc}"
        curr = f"{_CURRENT_DIR}/{svc}"
        cmd  = (f"[ -d '{sv}' ] && ln -sf '{sv}' '{curr}' && echo enabled "
                f"|| echo 'sv dir missing: {sv}' >&2")
        proc = self._chroot(["sh", "-c", cmd])
        result = self._result(svc, ServiceAction.ENABLE, proc)
        if "sv dir missing" in result.message:
            result.success = False
            result.message = (f"runit service dir '{sv}' not found. "
                              f"Install '{svc}-runit' first.")
        return result

    def disable_service(self, service: str) -> ServiceResult:
        svc  = self._clean_name(service)
        proc = self._chroot(["rm", "-f", f"{_CURRENT_DIR}/{svc}"])
        return self._result(svc, ServiceAction.DISABLE, proc)

    def configure_networking(self, use_nm: bool = True) -> list[str]:
        if use_nm:
            pkgs = ["networkmanager", "networkmanager-runit"]
            self.enable_service("NetworkManager")
        else:
            pkgs = ["dhcpcd", "dhcpcd-runit"]
            self.enable_service("dhcpcd")
        return pkgs

    def configure_time_sync(self) -> list[str]:
        self.enable_service(self.time_sync_service)
        return self.time_sync_packages

    def configure_display_manager(self, dm_service: str) -> ServiceResult:
        return self.enable_service(self._clean_name(dm_service))

    def set_default_target(self, graphical: bool = False) -> None:
        pass  # runit: enabling DM service is sufficient.

    def translate_package(self, base_name: str) -> str:
        _map = {
            "networkmanager": "networkmanager-runit",
            "dhcpcd":         "dhcpcd-runit",
            "sshd":           "openssh-runit",
            "cronie":         "cronie-runit",
            "sddm":           "sddm-runit",
            "gdm":            "gdm-runit",
            "lightdm":        "lightdm-runit",
            "cups":           "cups-runit",
            "bluetooth":      "bluez-runit",
            "ufw":            "ufw-runit",
            "openntpd":       "openntpd-runit",
        }
        return _map.get(base_name.lower(), base_name)
