"""
artixinstall.lib.init
~~~~~~~~~~~~~~~~~~~~~

Init-system abstraction layer.

Every init-specific action in the installer goes through the interfaces
defined here.  Concrete backends live in the same package:

    openrc.py   – OpenRC  (rc-update / rc-service)
    runit.py    – runit   (sv / service symlinks)
    s6.py       – s6      (s6-rc / contents.d markers)
    dinit.py    – dinit   (dinit.d boot.d symlinks)

Public API
----------
    InitType                     Enum of the four supported inits
    InitBackend                  Abstract base class (re-exported)
    ServiceAction                Enum for enable/disable/start/stop
    ServiceResult                Dataclass result type
    get_backend(init_type, path) Factory returning concrete backend
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .base import InitBackend, ServiceAction, ServiceResult  # noqa: F401


class InitType(str, Enum):
    OpenRC = "openrc"
    Runit  = "runit"
    S6     = "s6"
    Dinit  = "dinit"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def display_names(cls) -> list[str]:
        return [m.value for m in cls]


def get_backend(init_type: InitType, target: Path) -> InitBackend:
    """Return the concrete backend for *init_type* operating on *target*."""
    from .openrc import OpenRCBackend
    from .runit  import RunitBackend
    from .s6     import S6Backend
    from .dinit  import DinitBackend

    _MAP: dict[InitType, type[InitBackend]] = {
        InitType.OpenRC: OpenRCBackend,
        InitType.Runit:  RunitBackend,
        InitType.S6:     S6Backend,
        InitType.Dinit:  DinitBackend,
    }
    cls = _MAP.get(init_type)
    if cls is None:
        raise ValueError(f"Unknown init type: {init_type!r}. "
                         f"Supported: {list(_MAP.keys())}")
    return cls(target=target)
