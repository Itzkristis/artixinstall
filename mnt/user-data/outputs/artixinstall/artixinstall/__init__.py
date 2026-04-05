"""
artixinstall
============

Artix Linux installer – a fork of archlinux/archinstall adapted for
Artix's init-agnostic package ecosystem.

Quick start
-----------
    python -m artixinstall          # run the guided installer
    python -m artixinstall --help   # show all options

Architecture
------------
The installer delegates all init-specific behaviour to one of four
backends:

    OpenRCBackend   – rc-update / rc-service
    RunitBackend    – service symlinks
    S6Backend       – s6-rc contents.d markers  [EXPERIMENTAL]
    DinitBackend    – dinit.d boot.d symlinks

Everything else is inherited from upstream archinstall unchanged.
"""

from artixinstall.lib.init import InitType, get_backend

__version__ = "0.1.0-mvp"
__all__ = ["InitType", "get_backend", "__version__"]
