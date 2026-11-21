"""Backward-compat re-export — prefer ``from happyclaw_harness.slash import ...``."""

from happyclaw_harness.slash.core import (
    RuntimeSlashDispatcher,
    build_runtime_dispatcher,
)

__all__ = ["RuntimeSlashDispatcher", "build_runtime_dispatcher"]
