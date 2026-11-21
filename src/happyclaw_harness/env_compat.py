"""Read ``HAPPYCLAW_*`` environment variables with a deprecated ``OCTOP_*`` fallback.

HappyClaw Harness renamed its environment-variable prefix from ``OCTOP_`` to
``HAPPYCLAW_`` in 1.0.13. The new name always wins; when only the old name is
set its value is still honoured, with a :class:`DeprecationWarning` per variable
so an existing deployment keeps working through the upgrade.
"""

from __future__ import annotations

import os
import warnings

PREFIX = "HAPPYCLAW_"
LEGACY_PREFIX = "OCTOP_"

_deprecated_names: set[str] = set()


def legacy_name(name: str) -> str:
    """Return the pre-1.0.13 spelling of a ``HAPPYCLAW_*`` variable name."""
    if not name.startswith(PREFIX):
        return name
    return LEGACY_PREFIX + name[len(PREFIX) :]


def get_env(name: str, default: str | None = None) -> str | None:
    """Return the value of *name*, falling back to its deprecated ``OCTOP_*`` twin."""
    if name in os.environ:
        return os.environ[name]
    deprecated = legacy_name(name)
    if deprecated != name and deprecated in os.environ:
        _warn_deprecated(deprecated, name)
        return os.environ[deprecated]
    return default


def is_set(name: str) -> bool:
    """Return whether *name* or its deprecated ``OCTOP_*`` twin is present."""
    return name in os.environ or legacy_name(name) in os.environ


def _warn_deprecated(deprecated: str, name: str) -> None:
    if deprecated in _deprecated_names:
        return
    _deprecated_names.add(deprecated)
    warnings.warn(
        f"{deprecated} is deprecated and will stop working in a future release; use {name} instead.",
        DeprecationWarning,
        stacklevel=3,
    )
