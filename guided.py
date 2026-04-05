"""
artixinstall/scripts/guided.py

Artix-flavoured guided installer.

This is a fork of archinstall/scripts/guided.py with the minimum changes
needed to support Artix:

  1. Init system selection menu (new — inserted after kernel selection)
  2. ArtixInstaller replaces Installer
  3. enable_service() calls go through the backend
  4. Time sync goes through the backend
  5. Display manager goes through the backend
  6. "archinstall" branding replaced with "artixinstall"

Everything else — disk selection, partition layout, locale, hostname,
user creation, bootloader — is IDENTICAL to upstream guided.py.

To update from upstream:
  diff archinstall/scripts/guided.py artixinstall/scripts/guided.py
  Apply only the hunks related to ArtixInstaller, init selection,
  and service management.  Leave everything else alone.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure artixinstall's lib is importable
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# ---------------------------------------------------------------------------
# Upstream archinstall imports (inherited verbatim)
# ---------------------------------------------------------------------------
import archinstall
from archinstall import (
    Installer,           # we will subclass this → ArtixInstaller
    ConfigurationOutput,
    Profile,
    User,
    disk,
    locale,
    models,
    interactions,
)
from archinstall.lib.interactions import (
    ask_for_bootloader,
    ask_for_additional_packages_to_install,
    ask_for_swap,
)
from archinstall.tui import (
    MenuItemGroup,
    MenuItem,
    SelectMenu,
    Tui,
)

# ---------------------------------------------------------------------------
# Artix-specific imports
# ---------------------------------------------------------------------------
from artixinstall.lib.artix_installer import ArtixInstaller
from artixinstall.lib.init_backends.base import InitBackend

log = logging.getLogger("artixinstall")

# ---------------------------------------------------------------------------
# Artix branding
# ---------------------------------------------------------------------------
BANNER = r"""
  ___         _   _      
 / _ \  _ __| |_(_)_  __
| | | || '__| __| \ \/ /
| |_| || |  | |_| |>  < 
 \___/ |_|   \__|_/_/\_\

  artixinstall — Arch's archinstall, adapted for Artix Linux
  Upstream: https://github.com/archlinux/archinstall
  Fork:     https://github.com/YOUR_ORG/artixinstall
"""


# ---------------------------------------------------------------------------
# New interaction: Init system selection
# ---------------------------------------------------------------------------

_INIT_MENU_ITEMS = [
    MenuItem(
        "openrc",
        description=(
            "OpenRC — dependency-based init (Gentoo-style), "
            "simple runlevels, rc-update/rc-service"
        ),
    ),
    MenuItem(
        "runit",
        description=(
            "runit — daemontools-compatible process supervision, "
            "very fast boot, sv commands"
        ),
    ),
    MenuItem(
        "s6",
        description=(
            "s6 — modular process supervision with s6-rc service manager, "
            "fine-grained dependency graph"
        ),
    ),
    MenuItem(
        "dinit",
        description=(
            "dinit — simple, dependency-aware init, "
            "dinitctl management, good dependency ordering"
        ),
    ),
]


def ask_for_init_system(config: archinstall.GlobalConfig) -> str:
    """
    Present an interactive menu to select the Artix init system.

    Returns the init system name: openrc | runit | s6 | dinit
    """
    # Allow headless/JSON override
    if hasattr(config, "init_system") and config.init_system:
        log.info("Init system from config: %s", config.init_system)
        return config.init_system

    print("\n[artixinstall] Select init system:")
    for i, item in enumerate(_INIT_MENU_ITEMS, 1):
        print(f"  {i}. {item.value:<8}  {item.description}")
    print()

    while True:
        choice = input("Enter number or name [1-4]: ").strip().lower()

        # Accept number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(_INIT_MENU_ITEMS):
                selected = _INIT_MENU_ITEMS[idx].value
                print(f"→ Selected init system: {selected}\n")
                return selected

        # Accept name directly
        valid = {item.value for item in _INIT_MENU_ITEMS}
        if choice in valid:
            print(f"→ Selected init system: {choice}\n")
            return choice

        print(f"Invalid choice '{choice}'. Enter 1–4 or one of: {', '.join(valid)}")


# ---------------------------------------------------------------------------
# Main guided installation flow
# ---------------------------------------------------------------------------

def _guided_install() -> None:
    print(BANNER)

    # -----------------------------------------------------------------
    # [UPSTREAM] Load / save config  (unchanged from archinstall)
    # -----------------------------------------------------------------
    archinstall.parse_args()
    config = archinstall.GlobalConfig()
    config.load_config(archinstall.arguments.get("config"))
    creds = archinstall.CredentialStore()
    creds.load_config(archinstall.arguments.get("creds"))

    # -----------------------------------------------------------------
    # [UPSTREAM] Language, keyboard, mirror region (unchanged)
    # -----------------------------------------------------------------
    config.language = interactions.ask_for_a_language(config.language)
    config.keyboard_layout = interactions.ask_for_keyboard_layout(config.keyboard_layout)
    config.mirror_region = interactions.ask_for_mirror_region(config.mirror_region)

    # -----------------------------------------------------------------
    # [UPSTREAM] Disk layout (unchanged — disk lib is init-agnostic)
    # -----------------------------------------------------------------
    storage_device = interactions.select_disk_config(config.disk_config)
    config.disk_config = storage_device

    # -----------------------------------------------------------------
    # [UPSTREAM] Disk encryption (unchanged)
    # -----------------------------------------------------------------
    disk_encryption = interactions.ask_for_disk_encryption(config.disk_config)
    config.disk_encryption = disk_encryption

    # -----------------------------------------------------------------
    # [UPSTREAM] Bootloader (unchanged)
    # -----------------------------------------------------------------
    bootloader = ask_for_bootloader(
        config.bootloader,
        config.disk_config,
    )
    config.bootloader = bootloader

    # -----------------------------------------------------------------
    # [UPSTREAM] Swap (unchanged)
    # -----------------------------------------------------------------
    config.swap = ask_for_swap()

    # -----------------------------------------------------------------
    # [UPSTREAM] Hostname (unchanged)
    # -----------------------------------------------------------------
    config.hostname = interactions.ask_for_hostname(config.hostname)

    # -----------------------------------------------------------------
    # [UPSTREAM] Root password (unchanged)
    # -----------------------------------------------------------------
    creds.root_password = interactions.ask_for_root_password()

    # -----------------------------------------------------------------
    # [UPSTREAM] User creation (unchanged)
    # -----------------------------------------------------------------
    config.users = interactions.ask_for_user_account(
        creds,
        config.users,
    )

    # -----------------------------------------------------------------
    # [UPSTREAM] Profile / desktop (unchanged)
    # -----------------------------------------------------------------
    config.profile = interactions.ask_for_profile(config.profile)

    # -----------------------------------------------------------------
    # [UPSTREAM] Audio (unchanged)
    # -----------------------------------------------------------------
    config.audio = interactions.ask_for_audio_selection(config.profile)

    # -----------------------------------------------------------------
    # [UPSTREAM] Kernel selection (unchanged)
    # -----------------------------------------------------------------
    config.kernels = interactions.select_kernel(config.kernels)

    # -----------------------------------------------------------------
    # [ARTIX NEW] Init system selection — inserted here, after kernel
    # -----------------------------------------------------------------
    config.init_system = ask_for_init_system(config)
    init_backend = InitBackend.from_string(config.init_system)

    # -----------------------------------------------------------------
    # [UPSTREAM] Additional packages (unchanged)
    # -----------------------------------------------------------------
    config.packages = ask_for_additional_packages_to_install(config.packages)

    # -----------------------------------------------------------------
    # [UPSTREAM] Network configuration (unchanged interaction)
    # -----------------------------------------------------------------
    config.network_config = interactions.ask_for_network_configuration(
        config.network_config
    )

    # -----------------------------------------------------------------
    # [UPSTREAM] Timezone, NTP (upstream asks; we override the action)
    # -----------------------------------------------------------------
    config.timezone = interactions.ask_for_timezone(config.timezone)
    # NOTE: We do NOT use archinstall's NTP/timedatectl path.
    #       ArtixInstaller.setup_time_sync() handles it via the backend.

    # -----------------------------------------------------------------
    # [UPSTREAM] Review & confirm (unchanged)
    # -----------------------------------------------------------------
    ConfigurationOutput(config).show_preview()
    if not interactions.ask_for_confirmation("Proceed with installation?"):
        log.info("Installation cancelled by user.")
        return

    # Save config (unchanged)
    ConfigurationOutput(config).save(
        archinstall.arguments.get("config", "user_configuration.json"),
        creds,
        archinstall.arguments.get("creds", "user_credentials.json"),
    )

    # -----------------------------------------------------------------
    # [ARTIX MODIFIED] Perform the installation
    # Use ArtixInstaller instead of Installer
    # -----------------------------------------------------------------
    fs_handler = disk.FilesystemHandler(
        config.disk_config,
        config.disk_encryption,
    )
    fs_handler.perform_filesystem_operations()

    with ArtixInstaller(
        target=archinstall.storage.get("MOUNT_POINT", "/mnt"),
        disk_config=config.disk_config,
        disk_encryption=config.disk_encryption,
        base_packages=config.packages,
        kernels=config.kernels,
        # Artix-specific
        init_backend=init_backend,
    ) as installation:

        # [ARTIX MODIFIED] Use artix minimal_installation
        installation.minimal_installation()

        # [ARTIX MODIFIED] Time sync via backend (not systemd-timesyncd)
        installation.setup_time_sync()

        # [UPSTREAM] Locale, hostname, keyboard — unchanged
        if config.mirror_region:
            installation.set_mirrors(config.mirror_region)
        installation.set_locale(config.locale)
        installation.set_timezone(config.timezone)
        installation.set_hostname(config.hostname)
        installation.set_keyboard_layout(config.keyboard_layout)

        # [UPSTREAM] Bootloader — unchanged (grub/bootctl are runtime-agnostic)
        installation.add_bootloader(config.bootloader)

        # [UPSTREAM] Swap — unchanged
        if config.swap:
            installation.setup_swap("zram")

        # [ARTIX MODIFIED] Networking via backend
        if config.network_config:
            installation.configure_nic(config.network_config)

        # [UPSTREAM] Users and passwords — unchanged
        if creds.root_password:
            installation.set_root_password(creds.root_password)
        for user in config.users:
            installation.create_user(user)

        # [UPSTREAM] Profile installation — unchanged
        # (Profile installs DE packages; DM enable goes through our backend)
        if config.profile:
            installation.install_profile(config.profile)

            # [ARTIX NEW] Enable elogind for desktop sessions
            installation.enable_elogind()

            # [ARTIX MODIFIED] Enable display manager via backend
            dm = _resolve_display_manager(config.profile)
            if dm:
                installation.install_display_manager(dm)

        # [UPSTREAM] SSH, additional services — unchanged interaction,
        #            but enable_service() goes through our backend override
        if interactions.ask_to_configure_network():
            pass  # handled above

        log.info("=== artixinstall complete ===")
        log.info(
            "You may now reboot into your Artix (%s) installation.",
            init_backend.name,
        )


def _resolve_display_manager(profile) -> str | None:
    """
    Resolve the default display manager for a given profile.

    This mirrors upstream's profile DM mapping but is maintained separately
    so we can route through the init backend without modifying Profile classes.
    """
    if profile is None:
        return None

    profile_name = getattr(profile, "name", "").lower()

    dm_map = {
        "kde": "sddm",
        "plasma": "sddm",
        "gnome": "gdm",
        "xfce": "lightdm",
        "lxqt": "sddm",
        "lxde": "lxdm",
        "mate": "lightdm",
        "cinnamon": "lightdm",
        "i3": "lightdm",
        "sway": None,   # Wayland compositors typically manage their own session
        "hyprland": None,
    }

    for key, dm in dm_map.items():
        if key in profile_name:
            return dm

    # Default: if a desktop profile is selected but we don't know it, use lightdm
    if profile_name and profile_name not in ("server", "minimal", "base"):
        log.warning(
            "Unknown profile '%s'; defaulting display manager to lightdm",
            profile_name,
        )
        return "lightdm"

    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _guided_install()
