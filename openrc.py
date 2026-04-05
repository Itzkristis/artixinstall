"""artixinstall.lib.init.openrc – OpenRC backend."""
from __future__ import annotations
from pathlib import Path
from .base import InitBackend, ServiceAction, ServiceResult


class OpenRCBackend(InitBackend):
    """OpenRC backend: rc-update add/del inside arch-chroot."""

    def __init__(self, target: Path) -> None:
        super().__init__(target)

    @property
    def name(self) -> str:
        return "OpenRC"

    @property
    def base_packages(self) -> list[str]:
        return ["base", "openrc", "artix-openrc-meta"]

    @property
    def time_sync_service(self) -> str:
        return "openntpd"

    @property
    def time_sync_packages(self) -> list[str]:
        return ["openntpd", "openntpd-openrc"]

    def enable_service(self, service: str, runlevel: str = "default") -> ServiceResult:
        svc  = self._clean_name(service)
        proc = self._chroot(["rc-update", "add", svc, runlevel])
        result = self._result(svc, ServiceAction.ENABLE, proc)
        if not result.success and "already in runlevel" in result.message:
            result.success = True
        return result

    def disable_service(self, service: str) -> ServiceResult:
        svc  = self._clean_name(service)
        proc = self._chroot(["rc-update", "del", svc])
        return self._result(svc, ServiceAction.DISABLE, proc)

    def configure_networking(self, use_nm: bool = True) -> list[str]:
        if use_nm:
            pkgs = ["networkmanager", "networkmanager-openrc"]
            self.enable_service("NetworkManager")
        else:
            pkgs = ["dhcpcd", "dhcpcd-openrc"]
            self.enable_service("dhcpcd")
        return pkgs

    def configure_time_sync(self) -> list[str]:
        self.enable_service(self.time_sync_service)
        return self.time_sync_packages

    def configure_display_manager(self, dm_service: str) -> ServiceResult:
        return self.enable_service(self._clean_name(dm_service))

    def set_default_target(self, graphical: bool = False) -> None:
        pass  # OpenRC: enabling DM in 'default' runlevel is sufficient.

    def translate_package(self, base_name: str) -> str:
        _map = {
            "networkmanager": "networkmanager-openrc",
            "dhcpcd":         "dhcpcd-openrc",
            "sshd":           "openssh-openrc",
            "cronie":         "cronie-openrc",
            "sddm":           "sddm-openrc",
            "gdm":            "gdm-openrc",
            "lightdm":        "lightdm-openrc",
            "cups":           "cups-openrc",
            "bluetooth":      "bluez-openrc",
            "ufw":            "ufw-openrc",
            "openntpd":       "openntpd-openrc",
        }
        return _map.get(base_name.lower(), base_name)
