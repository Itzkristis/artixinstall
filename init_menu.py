"""
artixinstall.lib.init_menu
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Init system selection TUI menu.

Hooks into the upstream archinstall menu framework (AbstractMenu /
MenuItem) so the init-system picker feels native within the guided flow.

The menu is injected as a new item into GlobalMenu between "Locales" and
"Disk configuration" – matching the Artix-specific setup phase.

Usage
-----
    from artixinstall.lib.init_menu import select_init_system
    init_type = select_init_system(current=InitType.OpenRC)
"""

from __future__ import annotations

from typing import Optional

# Upstream TUI components
from archinstall.tui.ui.menu_item import MenuItem, MenuItemGroup
from archinstall.tui.ui.result import ResultType
from archinstall.lib.menu.helpers import Selection

from artixinstall.lib.init import InitType


# ---------------------------------------------------------------------------
# Init system metadata shown in the menu
# ---------------------------------------------------------------------------

_INIT_INFO: dict[InitType, dict[str, str]] = {
    InitType.OpenRC: {
        "label":   "OpenRC",
        "desc":    "Traditional init system used in Gentoo / Artix. Mature, "
                   "well-documented, large package support in Artix repos.",
        "status":  "stable",
    },
    InitType.Runit: {
        "label":   "runit",
        "desc":    "Minimal, fast supervisor-based init. Used by Void Linux. "
                   "Service scripts live in /etc/runit/sv/. Very reliable.",
        "status":  "stable",
    },
    InitType.S6: {
        "label":   "s6",
        "desc":    "s6 + s6-rc supervision suite. Highly reliable and correct "
                   "by design. Smaller Artix package coverage than OpenRC/runit.",
        "status":  "experimental",
    },
    InitType.Dinit: {
        "label":   "dinit",
        "desc":    "Dependency-aware init inspired by systemd but without "
                   "the complexity. Growing Artix package support.",
        "status":  "experimental",
    },
}


def _preview_init(item: MenuItem) -> Optional[str]:
    """Preview callback: show description and package-support status."""
    if item.value is None:
        return None
    info = _INIT_INFO.get(item.value, {})
    status  = info.get("status", "unknown")
    desc    = info.get("desc",   "No description available.")
    marker  = "✓ Stable" if status == "stable" else "⚠ Experimental (MVP)"
    return f"{marker}\n\n{desc}"


async def select_init_system(current: InitType = InitType.OpenRC) -> InitType:
    """
    Show the init-system picker and return the user's choice.

    Parameters
    ----------
    current:
        Pre-selected init type (shown as the default selection).

    Returns
    -------
    InitType
        The selected init system.
    """
    items = [
        MenuItem(
            text=f"{_INIT_INFO[t]['label']}",
            value=t,
            preview_action=_preview_init,
        )
        for t in InitType
    ]

    group = MenuItemGroup(items, sort_items=False)
    group.set_selected_by_value(current)

    result = await Selection[InitType](
        group,
        multi=False,
        allow_reset=False,
        allow_skip=False,
        preview_location="right",
        header="Select init system\n"
               "──────────────────────────────────────────────────────────\n"
               "This determines how services are started and managed.\n"
               "OpenRC is recommended for first-time Artix users.\n"
    ).show()

    match result.type_:
        case ResultType.Selection:
            return result.get_value()
        case _:
            # Should not happen with allow_reset=False, allow_skip=False
            return current


def make_init_menu_item(artix_config) -> MenuItem:  # type: ignore[type-arg]
    """
    Factory: return a MenuItem that can be inserted into GlobalMenu.

    Parameters
    ----------
    artix_config:
        The ArtixConfig instance being built by the guided installer.
    """
    async def _action(_current) -> InitType:  # type: ignore[no-untyped-def]
        chosen = await select_init_system(artix_config.init_type)
        artix_config.init_type = chosen
        return chosen

    def _preview(_item: MenuItem) -> Optional[str]:
        info = _INIT_INFO.get(artix_config.init_type, {})
        return (
            f"Selected: {info.get('label', artix_config.init_type.value)}\n"
            f"Status:   {info.get('status', 'unknown').capitalize()}\n\n"
            f"{info.get('desc', '')}"
        )

    return MenuItem(
        text="Init system",
        value=artix_config.init_type,
        action=_action,
        preview_action=_preview,
        key="init_type",
    )
