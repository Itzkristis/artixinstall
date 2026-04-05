"""
artixinstall.lib.installer
~~~~~~~~~~~~~~~~~~~~~~~~~~

ArtixInstaller
    Drop-in replacement for upstream archinstall.lib.installer.Installer.

Strategy
    * Subclass upstream Installer (not replace it).
    * Override only the methods that contain systemd-specific behaviour.
    * Delegate all init-specific actions to the selected InitBackend.
    * Keep the public method signatures identical so the guided script
      (scripts/guided.py) works unchanged.

Overridden methods (compared to upstream)
    __init__                – accept init_type; build backend; patch hooks
    enable_service          – delegate to InitBackend instead of systemctl
    disable_service         – delegate to InitBackend instead of systemctl
    activate_time_sync      – use init-appropriate NTP daemon
    enable_periodic_trim    – replaced with init-aware fstrim handling
    configure_nic           – write /etc/NetworkManager/ conf instead of
                              systemd-networkd .network files
    copy_iso_network_config – strip all systemd-networkd / resolved logic
    minimal_installation    – inject Artix base packages; strip systemd pkg
    _add_systemd_bootloader – blocked (systemd-boot needs systemd on live)

NOT overridden (upstream works fine)
    * genfstab         – format-agnostic
    * set_hostname     – writes /etc/hostname
    * set_locale       – writes locale.gen
    * set_timezone     – symlinks /etc/localtime
    * create_users     – arch-chroot useradd
    * set_user_password – arch-chroot chpasswd
    * add_bootloader   – GRUB path is init-agnostic; systemd-boot blocked
    * mkinitcpio       – Artix uses mkinitcpio; hooks are patched in __init__
    * mount_ordered_layout – disk-layer; unchanged
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

# ── Upstream import ───────────────────────────────────────────────────────────
# We import the full upstream Installer.  artixinstall ships the upstream
# archinstall package as a vendored dependency (or installed separately).
try:
    from archinstall.lib.installer import (
        Installer as _UpstreamInstaller,
        accessibility_tools_in_use,
        run_custom_user_commands,
    )
    from archinstall.lib.exceptions import ServiceException, SysCallError
    from archinstall.lib.output import debug, error, info, warn
    from archinstall.lib.models.device import DiskLayoutConfiguration
    from archinstall.lib.models.network import Nic
    from archinstall.lib.models.packages import Repository
    from archinstall.lib.pacman.config import PacmanConfig
    from archinstall.lib.plugins import plugins
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "artixinstall requires the upstream 'archinstall' package to be "
        "installed.  Run: pip install archinstall"
    ) from exc

# ── Artix-specific imports ────────────────────────────────────────────────────
from artixinstall.lib.init import InitType, get_backend
from artixinstall.lib.init.base import InitBackend, ServiceAction, ServiceResult
from artixinstall.lib.packages import ArtixPackages


class ArtixInstaller(_UpstreamInstaller):
    """
    Artix-aware installer.

    All systemd assumptions in the upstream class are overridden here.
    Everything that is init-agnostic is inherited unchanged.

    Parameters
    ----------
    target:
        Installation root (e.g. ``Path('/mnt')``).
    disk_config:
        Disk layout from the disk configuration menu.
    init_type:
        User's chosen init system (OpenRC / runit / s6 / dinit).
    kernels:
        List of kernel package names to install.
    silent:
        Suppress interactive prompts where possible.
    """

    def __init__(
        self,
        target: Path,
        disk_config: DiskLayoutConfiguration,
        init_type: InitType = InitType.OpenRC,
        base_packages: list[str] = [],
        kernels: list[str] | None = None,
        silent: bool = False,
    ) -> None:
        self.init_type  = init_type
        self._backend: InitBackend = get_backend(init_type, target)
        self._artix_pkgs = ArtixPackages(init_type)

        # Build Artix base packages before calling super().__init__
        # so that _base_packages is set correctly from the start.
        artix_base = self._artix_pkgs.base_system()
        merged_base = list(dict.fromkeys(artix_base + (base_packages or [])))

        super().__init__(
            target=target,
            disk_config=disk_config,
            base_packages=merged_base,
            kernels=kernels,
            silent=silent,
        )

        # ── Patch mkinitcpio hooks ────────────────────────────────────────
        # Upstream sets hooks=['base','systemd','autodetect',...]
        # Replace 'systemd' with 'udev' and 'sd-vconsole' with 'keymap'
        # because Artix uses the traditional initramfs hook set.
        self._hooks = [
            h.replace("systemd", "udev").replace("sd-vconsole", "keymap consolefont")
            for h in self._hooks
        ]
        # Deduplicate (the replacement can produce adjacent duplicates)
        seen: set[str] = set()
        clean_hooks: list[str] = []
        for h in self._hooks:
            for part in h.split():
                if part not in seen:
                    seen.add(part)
                    clean_hooks.append(part)
        self._hooks = clean_hooks

        info(f"ArtixInstaller initialised with init={init_type.value}, "
             f"hooks={self._hooks}")

    # ------------------------------------------------------------------ #
    # Service management – delegates entirely to the backend              #
    # ------------------------------------------------------------------ #

    def enable_service(self, services: str | list[str]) -> None:
        """
        Enable one or more services using the selected init backend.

        This replaces the upstream ``systemctl --root=<target> enable`` calls.
        """
        if isinstance(services, str):
            services = [services]

        for svc in services:
            info(f"[{self._backend.name}] Enabling service: {svc}")
            result: ServiceResult = self._backend.enable_service(svc)

            if result.success:
                debug(f"Service '{svc}' enabled successfully")
            else:
                warn(f"Could not enable '{svc}': {result.message}")
                # Non-fatal: log and continue.  The upstream raises
                # ServiceException here; we downgrade to a warning
                # because not every Artix init package may be present
                # in all repos at all times.

            for plugin in plugins.values():
                if hasattr(plugin, "on_service"):
                    plugin.on_service(svc)

    def disable_service(self, services_disable: str | list[str]) -> None:
        if isinstance(services_disable, str):
            services_disable = [services_disable]

        for svc in services_disable:
            info(f"[{self._backend.name}] Disabling service: {svc}")
            result = self._backend.disable_service(svc)
            if not result.success:
                warn(f"Could not disable '{svc}': {result.message}")

    # ------------------------------------------------------------------ #
    # Time synchronisation                                                 #
    # ------------------------------------------------------------------ #

    def activate_time_synchronization(self) -> None:
        """
        Install and enable an init-appropriate NTP daemon.

        Replaces upstream's hardcoded ``systemd-timesyncd`` enablement.
        """
        info(
            f"[{self._backend.name}] Activating time synchronisation via "
            f"{self._backend.time_sync_service}"
        )
        ntp_pkgs = self._backend.configure_time_sync()
        self.add_additional_packages(ntp_pkgs)
        # configure_time_sync() already calls enable_service internally

    # ------------------------------------------------------------------ #
    # Periodic TRIM                                                        #
    # ------------------------------------------------------------------ #

    def enable_periodic_trim(self) -> None:
        """
        Enable periodic TRIM via a cron job instead of fstrim.timer.

        fstrim.timer is a systemd unit owned by util-linux on Arch.
        On Artix we use a weekly cron job which works with any init.
        """
        info("Enabling periodic TRIM via cron (replaces fstrim.timer)")
        cron_dir  = self.target / "etc" / "cron.weekly"
        cron_dir.mkdir(parents=True, exist_ok=True)
        cron_file = cron_dir / "fstrim"
        cron_file.write_text(
            "#!/bin/sh\n"
            "# Written by artixinstall – periodic SSD TRIM\n"
            "/sbin/fstrim --all --quiet-unsupported || true\n"
        )
        cron_file.chmod(0o755)
        debug("Wrote /etc/cron.weekly/fstrim")

        # Install cronie as the cron daemon (init-aware)
        cronie_svc_pkg = self._artix_pkgs.resolve("cronie")
        if cronie_svc_pkg:
            self.add_additional_packages(["cronie", cronie_svc_pkg])
            self.enable_service("cronie")

    # ------------------------------------------------------------------ #
    # Base installation override                                           #
    # ------------------------------------------------------------------ #

    def minimal_installation(
        self,
        optional_repositories: list[Repository] = [],
        mkinitcpio: bool = True,
        hostname: str | None = None,
        locale_config=None,
    ) -> None:
        """
        Artix-aware minimal installation.

        Differences from upstream:
        1.  Artix-specific pacman.conf is applied before pacstrap.
        2.  'systemd' is never added to the package list.
        3.  All init-meta packages are already in _base_packages (set in
            __init__).
        4.  enable_periodic_trim() uses our cron-based override.
        5.  The rest is delegated to super() unchanged.
        """
        # Remove any upstream injections of 'systemd' that may appear
        # via plugin hooks or future upstream changes.
        self._base_packages = [
            p for p in self._base_packages if p not in ("systemd", "systemd-libs")
        ]

        # Apply the Artix pacman.conf (repos, etc.) before strap
        self._apply_artix_pacman_conf(optional_repositories)

        # Let upstream handle the rest (pacstrap, locale, hostname, mkinitcpio)
        # but our overridden enable_periodic_trim() and enable_service() will
        # be called by super() transparently.
        super().minimal_installation(
            optional_repositories=optional_repositories,
            mkinitcpio=mkinitcpio,
            hostname=hostname,
            locale_config=locale_config,
        )

    # ------------------------------------------------------------------ #
    # Networking overrides                                                 #
    # ------------------------------------------------------------------ #

    def configure_nic(self, nic: Nic) -> None:
        """
        Write a NetworkManager keyfile instead of a systemd-networkd .network
        file.  NM is the recommended network manager on Artix.
        """
        nm_dir = self.target / "etc" / "NetworkManager" / "system-connections"
        nm_dir.mkdir(parents=True, exist_ok=True)

        conn_file = nm_dir / f"{nic.iface}.nmconnection"
        if nic.dhcp:
            content = (
                f"[connection]\n"
                f"id={nic.iface}\n"
                f"type=ethernet\n"
                f"interface-name={nic.iface}\n\n"
                f"[ipv4]\n"
                f"method=auto\n\n"
                f"[ipv6]\n"
                f"method=auto\n"
            )
        else:
            ip   = str(nic.ip) if nic.ip else ""
            gw   = str(nic.gateway) if nic.gateway else ""
            dns  = ",".join(str(d) for d in (nic.dns or []))
            content = (
                f"[connection]\n"
                f"id={nic.iface}\n"
                f"type=ethernet\n"
                f"interface-name={nic.iface}\n\n"
                f"[ipv4]\n"
                f"method=manual\n"
                f"addresses={ip}\n"
                f"gateway={gw}\n"
                f"dns={dns}\n\n"
                f"[ipv6]\n"
                f"method=auto\n"
            )
        conn_file.write_text(content)
        conn_file.chmod(0o600)
        debug(f"Wrote NM keyfile: {conn_file}")

    def copy_iso_network_config(self, enable_services: bool = False) -> bool:
        """
        Copy wireless PSK files from the live ISO and optionally enable NM.

        Drops all systemd-networkd / systemd-resolved logic.
        On Artix the ISO uses NetworkManager, so we just copy the NM state.
        """
        # Copy iwd PSK files if present (wireless pre-shared keys)
        if os.path.isdir("/var/lib/iwd/"):
            psk_files = [
                f for f in os.listdir("/var/lib/iwd/")
                if f.endswith(".psk")
            ]
            if psk_files:
                iwd_target = self.target / "var" / "lib" / "iwd"
                iwd_target.mkdir(parents=True, exist_ok=True)
                for psk in psk_files:
                    shutil.copy2(f"/var/lib/iwd/{psk}", iwd_target / psk)
                info(f"Copied {len(psk_files)} iwd PSK file(s)")

        # Copy live NM connections if present
        nm_src = "/etc/NetworkManager/system-connections/"
        if os.path.isdir(nm_src):
            nm_dst = self.target / "etc" / "NetworkManager" / "system-connections"
            nm_dst.mkdir(parents=True, exist_ok=True)
            for f in os.listdir(nm_src):
                shutil.copy2(f"{nm_src}{f}", nm_dst / f)
            info("Copied live NetworkManager connections to target")

        # Write a standard /etc/resolv.conf (no systemd-resolved symlink)
        resolv = self.target / "etc" / "resolv.conf"
        if not resolv.exists():
            resolv.write_text(
                "# Generated by artixinstall\n"
                "nameserver 1.1.1.1\n"
                "nameserver 8.8.8.8\n"
            )

        if enable_services:
            nm_pkgs = self._artix_pkgs.networking_packages(use_nm=True)
            self.add_additional_packages(nm_pkgs)

            def _post_enable_nm(*_):  # type: ignore[no-untyped-def]
                self.enable_service("NetworkManager")

            if not self._helper_flags.get("base", False):
                self.post_base_install.append(_post_enable_nm)
            else:
                _post_enable_nm()

        return True

    # ------------------------------------------------------------------ #
    # Bootloader – block systemd-boot, keep GRUB                          #
    # ------------------------------------------------------------------ #

    def _add_systemd_bootloader(self, *args, **kwargs) -> None:  # type: ignore[override]
        """
        systemd-boot is blocked on Artix because it requires systemd at
        runtime.  Redirect users to GRUB.
        """
        error(
            "systemd-boot (bootctl) is not supported by artixinstall because "
            "it requires systemd at runtime. Please choose GRUB as your "
            "bootloader instead."
        )
        raise SystemExit(
            "Unsupported bootloader: systemd-boot. Use GRUB on Artix."
        )

    # ------------------------------------------------------------------ #
    # Display manager                                                      #
    # ------------------------------------------------------------------ #

    def install_display_manager(self, dm: str) -> None:
        """
        Install and enable a display manager the Artix way.

        Parameters
        ----------
        dm:
            Logical DM name: 'sddm', 'gdm', 'lightdm', 'ly'.
        """
        info(f"[{self._backend.name}] Installing display manager: {dm}")
        pkgs = self._artix_pkgs.display_manager_packages(dm)
        self.add_additional_packages(pkgs)

        def _post_enable_dm(*_):  # type: ignore[no-untyped-def]
            result = self._backend.configure_display_manager(dm)
            if result.success:
                info(f"Display manager '{dm}' enabled")
            else:
                warn(f"Could not enable '{dm}': {result.message}")

        if not self._helper_flags.get("base", False):
            self.post_base_install.append(_post_enable_dm)
        else:
            _post_enable_dm()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _apply_artix_pacman_conf(
        self, optional_repositories: list[Repository] = []
    ) -> None:
        """
        Write /etc/pacman.conf on the *host* (before pacstrap) so that
        pacstrap pulls from Artix mirrors rather than Arch mirrors.

        In a real Artix live ISO this conf is already correct.  This method
        is a safety net for testing from an Arch live environment.
        """
        artix_conf = self.target.parent / "etc" / "pacman.conf.artix"
        target_conf = Path("/etc/pacman.conf")

        if artix_conf.exists():
            info("Applying Artix pacman.conf override")
            shutil.copy2(artix_conf, target_conf)
        else:
            debug(
                "No /etc/pacman.conf.artix found – assuming live environment "
                "already has correct Artix repos configured."
            )

    @property
    def backend(self) -> InitBackend:
        """Expose the active init backend for use in profiles / scripts."""
        return self._backend

    @property
    def artix_packages(self) -> ArtixPackages:
        """Expose the package resolver for use in profiles / scripts."""
        return self._artix_pkgs
