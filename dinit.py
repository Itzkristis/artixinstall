"""artixinstall.lib.init.dinit – dinit backend."""
from __future__ import annotations
from pathlib import Path
from .base import InitBackend, ServiceAction, ServiceResult

_DINIT_D      = "/etc/dinit.d"
_DINIT_BOOT_D = "/etc/dinit.d/boot.d"


class DinitBackend(InitBackend):
    """dinit backend: symlinks in /etc/dinit.d/boot.d/."""

    def __init__(self, target: Path) -> None:
        super().__init__(target)

    @property
    def name(self) -> str:
        return "dinit"

    @property
    def base_packages(self) -> list[str]:
        return ["base", "dinit", "artix-dinit-meta"]

    @property
    def time_sync_service(self) -> str:
        return "openntpd"

    @property
    def time_sync_packages(self) -> list[str]:
        return ["openntpd", "openntpd-dinit"]

    def enable_service(self, service: str, runlevel: str = "default") -> ServiceResult:
        svc  = self._clean_name(service)
        src  = f"{_DINIT_D}/{svc}"
        link = f"{_DINIT_BOOT_D}/{svc}"
        cmd  = f"mkdir -p '{_DINIT_BOOT_D}' && ln -sf '{src}' '{link}'"
        proc = self._chroot(["sh", "-c", cmd])
        return self._result(svc, ServiceAction.ENABLE, proc)

    def disable_service(self, service: str) -> ServiceResult:
        svc  = self._clean_name(service)
        proc = self._chroot(["rm", "-f", f"{_DINIT_BOOT_D}/{svc}"])
        return self._result(svc, ServiceAction.DISABLE, proc)

    def configure_networking(self, use_nm: bool = True) -> list[str]:
        if use_nm:
            pkgs = ["networkmanager", "networkmanager-dinit"]
            self.enable_service("NetworkManager")
        else:
            pkgs = ["dhcpcd", "dhcpcd-dinit"]
            self.enable_service("dhcpcd")
        return pkgs

    def configure_time_sync(self) -> list[str]:
        self.enable_service(self.time_sync_service)
        return self.time_sync_packages

    def configure_display_manager(self, dm_service: str) -> ServiceResult:
        return self.enable_service(self._clean_name(dm_service))

    def set_default_target(self, graphical: bool = False) -> None:
        pass  # dinit: boot.d symlinks drive auto-start.

    def translate_package(self, base_name: str) -> str:
        _map = {
            "networkmanager": "networkmanager-dinit",
            "dhcpcd":         "dhcpcd-dinit",
            "sshd":           "openssh-dinit",
            "cronie":         "cronie-dinit",
            "sddm":           "sddm-dinit",
            "gdm":            "gdm-dinit",
            "lightdm":        "lightdm-dinit",
            "cups":           "cups-dinit",
            "bluetooth":      "bluez-dinit",
            "ufw":            "ufw-dinit",
            "openntpd":       "openntpd-dinit",
        }
        return _map.get(base_name.lower(), base_name)
