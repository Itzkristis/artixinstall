"""
artixinstall.default_profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Artix-patched desktop profiles.

Strategy
    Inherit from upstream archinstall Profile subclasses.
    Override only what is init-specific:
        – packages list (swap systemd-flavoured pkgs for Artix equivalents)
        – post_install (use ArtixInstaller.install_display_manager)
        – services (the service names stay the same; the backend
          translates them to the correct init-specific commands)

The upstream profile hierarchy is:
    Profile → DesktopProfile → GnomeProfile / PlasmaProfile / Xfce4Profile …

We inject a mixin (ArtixProfileMixin) that overrides post_install and
adjusts packages.  The mixin works with any upstream Profile subclass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

# ── Upstream profile imports ──────────────────────────────────────────────────
from archinstall.default_profiles.profile import GreeterType, Profile, ProfileType
from archinstall.default_profiles.desktops.gnome   import GnomeProfile   as _GnomeProfile
from archinstall.default_profiles.desktops.plasma  import PlasmaProfile  as _PlasmaProfile
from archinstall.default_profiles.desktops.xfce4   import Xfce4Profile   as _Xfce4Profile
from archinstall.default_profiles.desktops.mate    import MateProfile    as _MateProfile
from archinstall.default_profiles.desktops.lxqt    import LxqtProfile   as _LxqtProfile

if TYPE_CHECKING:
    from artixinstall.lib.installer import ArtixInstaller


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class ArtixProfileMixin:
    """
    Mixin applied to upstream Profile subclasses.

    Overrides post_install to use ArtixInstaller.install_display_manager()
    instead of the upstream enable_service(greeter.value) which uses
    systemctl.

    Usage
    -----
        class ArtixGnome(ArtixProfileMixin, _GnomeProfile):
            pass
    """

    def post_install(self, install_session: "ArtixInstaller") -> None:  # type: ignore[override]
        """Enable display manager via the init backend."""
        greeter: GreeterType | None = getattr(self, "default_greeter_type", None)
        if greeter is not None:
            dm_name = greeter.value  # e.g. 'sddm', 'gdm', 'lightdm-gtk-greeter'
            # Normalise: we only want the DM name, not the greeter theme
            dm_base = _dm_base_name(dm_name)
            install_session.install_display_manager(dm_base)

        # Call parent post_install if it does anything extra
        # (most upstream profiles have an empty post_install)
        try:
            super().post_install(install_session)  # type: ignore[misc]
        except Exception:
            pass


def _dm_base_name(greeter_value: str) -> str:
    """
    Map a GreeterType.value to the base DM package name.

        'lightdm-gtk-greeter'  → 'lightdm'
        'lightdm-slick-greeter'→ 'lightdm'
        'sddm'                 → 'sddm'
        'gdm'                  → 'gdm'
        'ly'                   → 'ly'
    """
    if greeter_value.startswith("lightdm"):
        return "lightdm"
    return greeter_value.split("-")[0] if "-" in greeter_value else greeter_value


# ---------------------------------------------------------------------------
# Concrete Artix desktop profiles
# ---------------------------------------------------------------------------

class ArtixGnomeProfile(ArtixProfileMixin, _GnomeProfile):
    """GNOME desktop profile for Artix."""


class ArtixPlasmaProfile(ArtixProfileMixin, _PlasmaProfile):
    """KDE Plasma desktop profile for Artix."""


class ArtixXfce4Profile(ArtixProfileMixin, _Xfce4Profile):
    """Xfce4 desktop profile for Artix."""

    @property
    @override
    def default_greeter_type(self) -> GreeterType:
        return GreeterType.Lightdm


class ArtixMateProfile(ArtixProfileMixin, _MateProfile):
    """MATE desktop profile for Artix."""


class ArtixLxqtProfile(ArtixProfileMixin, _LxqtProfile):
    """LXQt desktop profile for Artix."""


# ---------------------------------------------------------------------------
# Profile registry
# ---------------------------------------------------------------------------
# Profiles registered here are used by artixinstall's profile_handler.
# They replace the equivalent upstream profiles.

ARTIX_DESKTOP_PROFILES: list[type[Profile]] = [
    ArtixGnomeProfile,
    ArtixPlasmaProfile,
    ArtixXfce4Profile,
    ArtixMateProfile,
    ArtixLxqtProfile,
]
