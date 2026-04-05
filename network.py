"""
artixinstall.lib.network
~~~~~~~~~~~~~~~~~~~~~~~~~

Artix-aware network configuration handler.

Replaces upstream archinstall/lib/network/network_handler.py.

Key changes versus upstream
    * All systemd-networkd and systemd-resolved references removed.
    * Network stack: NetworkManager (preferred) or dhcpcd (minimal).
    * Service enablement goes through the ArtixInstaller backend.
    * Wireless support: iwd or wpa_supplicant, both via NM.
    * Manual NIC configuration writes NM keyfiles, not .network files.

Usage
-----
    from artixinstall.lib.network import install_network_config
    install_network_config(network_config, installation, profile_config)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from archinstall.lib.models.network import NetworkConfiguration, NicType
from archinstall.lib.models.profile import ProfileConfiguration
from archinstall.lib.output import debug, info, warn

if TYPE_CHECKING:
    from artixinstall.lib.installer import ArtixInstaller


def install_network_config(
    network_config: NetworkConfiguration,
    installation: "ArtixInstaller",
    profile_config: ProfileConfiguration | None = None,
) -> None:
    """
    Configure networking for the installed system.

    Mirrors the signature of upstream ``install_network_config`` so
    guided.py can call this without modification.
    """
    match network_config.type:
        case NicType.ISO:
            _configure_iso_network(installation)

        case NicType.NM | NicType.NM_IWD:
            _configure_network_manager(
                installation,
                use_iwd=(network_config.type == NicType.NM_IWD),
                desktop=bool(
                    profile_config
                    and profile_config.profile
                    and profile_config.profile.is_desktop_profile()
                ),
            )

        case NicType.MANUAL:
            _configure_manual_nics(installation, network_config)

        case _:
            warn(f"Unknown network type: {network_config.type!r} – skipping")


# ---------------------------------------------------------------------------
# Individual configurators
# ---------------------------------------------------------------------------

def _configure_iso_network(installation: "ArtixInstaller") -> None:
    """
    Copy the live ISO network config to the target.

    On a real Artix ISO this picks up NM connections and iwd PSKs.
    The ArtixInstaller.copy_iso_network_config() method handles this
    without any systemd-networkd / systemd-resolved involvement.
    """
    info("Copying ISO network configuration to target")
    installation.copy_iso_network_config(enable_services=True)


def _configure_network_manager(
    installation: "ArtixInstaller",
    use_iwd: bool = False,
    desktop: bool = False,
) -> None:
    """Install and enable NetworkManager (with optional iwd backend)."""
    pkgs = installation.artix_packages.networking_packages(use_nm=True)

    if use_iwd:
        iwd_svc_pkg = installation.artix_packages.resolve("iwd")
        pkgs.extend(filter(None, ["iwd", iwd_svc_pkg]))
    else:
        pkgs.append("wpa_supplicant")

    if desktop:
        pkgs.append("network-manager-applet")

    # Remove duplicates while preserving order
    seen: set[str] = set()
    pkgs = [p for p in pkgs if p not in seen and not seen.add(p)]  # type: ignore[func-returns-value]

    installation.add_additional_packages(pkgs)
    installation.enable_service("NetworkManager")

    if use_iwd:
        _configure_nm_iwd_backend(installation)
        # iwd must NOT be in its own runlevel when managed by NM
        installation.disable_service("iwd")

    info(f"NetworkManager configured (iwd_backend={use_iwd})")


def _configure_nm_iwd_backend(installation: "ArtixInstaller") -> None:
    """Write the NM backend config that tells it to use iwd for WiFi."""
    nm_conf_dir = installation.target / "etc" / "NetworkManager" / "conf.d"
    nm_conf_dir.mkdir(parents=True, exist_ok=True)
    conf_file = nm_conf_dir / "wifi_backend.conf"
    conf_file.write_text("[device]\nwifi.backend=iwd\n")
    debug(f"Wrote NM iwd backend config: {conf_file}")


def _configure_manual_nics(
    installation: "ArtixInstaller",
    network_config: NetworkConfiguration,
) -> None:
    """
    Write NM keyfiles for manually-specified NICs and enable NM.

    Replaces upstream's systemd-networkd .network file generation.
    """
    for nic in network_config.nics:
        info(f"Configuring NIC: {nic.iface}")
        installation.configure_nic(nic)

    # Enable NM regardless of whether we wrote any keyfiles –
    # the user may add more interfaces post-install.
    nm_pkgs = installation.artix_packages.networking_packages(use_nm=True)
    installation.add_additional_packages(nm_pkgs)
    installation.enable_service("NetworkManager")
