"""
artixinstall.lib.packages
~~~~~~~~~~~~~~~~~~~~~~~~~~

Artix package mapping registry.

Package states
--------------
IDENTICAL   Same name as Arch; install verbatim.
RENAMED     Init-flavoured Artix name exists.
REPLACED    Artix uses a completely different package.
DROPPED     Does not exist in Artix; skip with a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class PkgState(Enum):
    IDENTICAL = auto()
    RENAMED   = auto()
    REPLACED  = auto()
    DROPPED   = auto()


@dataclass
class PkgMapping:
    arch_name: str
    state:     PkgState
    openrc:    Optional[str] = None
    runit:     Optional[str] = None
    s6:        Optional[str] = None
    dinit:     Optional[str] = None
    note:      str = ""

    def for_init(self, init_type) -> Optional[str]:
        if self.state == PkgState.DROPPED:
            return None
        if self.state == PkgState.IDENTICAL:
            return self.arch_name
        from artixinstall.lib.init import InitType
        mapping = {
            InitType.OpenRC: self.openrc,
            InitType.Runit:  self.runit,
            InitType.S6:     self.s6,
            InitType.Dinit:  self.dinit,
        }
        return mapping.get(init_type) or self.arch_name


_MAPPINGS: list[PkgMapping] = [
    # ── Init system ──────────────────────────────────────────────────────
    PkgMapping("systemd",           PkgState.DROPPED,
               note="Never install systemd on Artix"),
    PkgMapping("systemd-libs",      PkgState.REPLACED,
               openrc="elogind", runit="elogind", s6="elogind", dinit="elogind",
               note="elogind replaces systemd-logind"),

    # ── Networking ───────────────────────────────────────────────────────
    PkgMapping("networkmanager",    PkgState.RENAMED,
               openrc="networkmanager-openrc", runit="networkmanager-runit",
               s6="networkmanager-s6",         dinit="networkmanager-dinit"),
    PkgMapping("dhcpcd",            PkgState.RENAMED,
               openrc="dhcpcd-openrc",  runit="dhcpcd-runit",
               s6="dhcpcd-s6",          dinit="dhcpcd-dinit"),
    PkgMapping("iwd",               PkgState.RENAMED,
               openrc="iwd-openrc",  runit="iwd-runit",
               s6="iwd-s6",          dinit="iwd-dinit"),

    # ── Time sync ────────────────────────────────────────────────────────
    PkgMapping("systemd-timesyncd", PkgState.REPLACED,
               openrc="openntpd", runit="openntpd", s6="openntpd", dinit="openntpd",
               note="systemd-timesyncd does not exist on Artix; use openntpd"),

    # ── SSH ──────────────────────────────────────────────────────────────
    PkgMapping("openssh",           PkgState.RENAMED,
               openrc="openssh-openrc", runit="openssh-runit",
               s6="openssh-s6",         dinit="openssh-dinit"),

    # ── Display managers ─────────────────────────────────────────────────
    PkgMapping("sddm",    PkgState.RENAMED,
               openrc="sddm-openrc",    runit="sddm-runit",
               s6="sddm-s6",            dinit="sddm-dinit"),
    PkgMapping("gdm",     PkgState.RENAMED,
               openrc="gdm-openrc",     runit="gdm-runit",
               s6="gdm-s6",             dinit="gdm-dinit"),
    PkgMapping("lightdm", PkgState.RENAMED,
               openrc="lightdm-openrc", runit="lightdm-runit",
               s6="lightdm-s6",         dinit="lightdm-dinit"),
    PkgMapping("ly",      PkgState.IDENTICAL,
               note="ly bundles its own service file; no init variant needed"),

    # ── Bluetooth ────────────────────────────────────────────────────────
    PkgMapping("bluez",   PkgState.RENAMED,
               openrc="bluez-openrc",   runit="bluez-runit",
               s6="bluez-s6",           dinit="bluez-dinit"),

    # ── Printing ─────────────────────────────────────────────────────────
    PkgMapping("cups",    PkgState.RENAMED,
               openrc="cups-openrc",    runit="cups-runit",
               s6="cups-s6",            dinit="cups-dinit"),

    # ── Cron ─────────────────────────────────────────────────────────────
    PkgMapping("cronie",  PkgState.RENAMED,
               openrc="cronie-openrc",  runit="cronie-runit",
               s6="cronie-s6",          dinit="cronie-dinit"),

    # ── Firewall ─────────────────────────────────────────────────────────
    PkgMapping("ufw",       PkgState.RENAMED,
               openrc="ufw-openrc",       runit="ufw-runit",
               s6="ufw-s6",               dinit="ufw-dinit"),
    PkgMapping("firewalld", PkgState.RENAMED,
               openrc="firewalld-openrc", runit="firewalld-runit",
               s6="firewalld-s6",         dinit="firewalld-dinit"),

    # ── TRIM ─────────────────────────────────────────────────────────────
    PkgMapping("fstrim.timer", PkgState.REPLACED,
               openrc="util-linux-openrc", runit="util-linux-runit",
               s6="util-linux-s6",         dinit="util-linux-dinit",
               note="fstrim.timer is systemd; use cron.weekly/fstrim instead"),

    # ── Audio ────────────────────────────────────────────────────────────
    PkgMapping("pipewire",   PkgState.IDENTICAL,
               note="User-session audio; no init-specific pkg needed"),
    PkgMapping("wireplumber", PkgState.IDENTICAL),
]

_MAP_BY_ARCH: dict[str, PkgMapping] = {m.arch_name: m for m in _MAPPINGS}


class ArtixPackages:
    """Package resolver for a specific init system."""

    def __init__(self, init_type) -> None:
        self.init_type = init_type

    def resolve(self, arch_name: str) -> Optional[str]:
        """Translate Arch package name → correct Artix package, or None if DROPPED."""
        mapping = _MAP_BY_ARCH.get(arch_name)
        if mapping is None:
            return arch_name          # not in table → assume identical
        return mapping.for_init(self.init_type)

    def resolve_many(self, arch_names: list[str]) -> list[str]:
        """Resolve a list, dropping None results."""
        return [r for name in arch_names if (r := self.resolve(name)) is not None]

    def base_system(self) -> list[str]:
        """Minimal set of packages for a bootable Artix system."""
        from artixinstall.lib.init import InitType
        common = ["base", "base-devel", "linux-firmware", "elogind", "dbus", "sudo", "bash"]
        init_meta: dict = {
            InitType.OpenRC: ["openrc", "artix-openrc-meta"],
            InitType.Runit:  ["runit",  "artix-runit-meta"],
            InitType.S6:     ["s6", "s6-rc", "artix-s6-meta"],
            InitType.Dinit:  ["dinit", "artix-dinit-meta"],
        }
        return common + init_meta.get(self.init_type, [])

    def display_manager_packages(self, dm: str) -> list[str]:
        svc_pkg = self.resolve(dm)
        pkgs = [dm]
        if svc_pkg and svc_pkg != dm:
            pkgs.append(svc_pkg)
        return pkgs

    def networking_packages(self, use_nm: bool = True) -> list[str]:
        core = "networkmanager" if use_nm else "dhcpcd"
        svc  = self.resolve(core)
        return list(dict.fromkeys(p for p in [core, svc] if p))

    def get_state(self, arch_name: str) -> PkgState:
        m = _MAP_BY_ARCH.get(arch_name)
        return m.state if m else PkgState.IDENTICAL

    def get_note(self, arch_name: str) -> str:
        m = _MAP_BY_ARCH.get(arch_name)
        return m.note if m else ""


def get_full_mapping_table() -> list[dict]:
    """Return the full mapping table as a list of dicts (for display/debug)."""
    return [
        {
            "arch":   m.arch_name,
            "state":  m.state.name,
            "openrc": m.openrc or m.arch_name,
            "runit":  m.runit  or m.arch_name,
            "s6":     m.s6     or m.arch_name,
            "dinit":  m.dinit  or m.arch_name,
            "note":   m.note,
        }
        for m in _MAPPINGS
    ]
