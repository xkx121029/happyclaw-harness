"""ACP (Agent Client Protocol) client integration for delegated external agents."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from happyclaw_harness.acp.models import (
    ACPConfig,
    ACPConfigurationError,
    ACPErrors,
    ACPProtocolError,
    ACPRunnerConfig,
    ACPSessionError,
    ACPTransportError,
    SuspendedPermission,
)

if TYPE_CHECKING:
    from happyclaw_harness.acp.service import ACPService

# ``ACPService`` pulls the backends package, which imports the whole LangChain
# stack. Callers that only need the config dataclasses (``HarnessAgentConfig``
# does) must not pay for it, so the service resolves on first attribute access.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "ACPService": ("happyclaw_harness.acp.service", "ACPService"),
}


def __getattr__(name: str) -> object:  # pragma: no cover - thin re-export shim
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    return getattr(import_module(module_name), attr)


__all__ = [
    "ACPConfig",
    "ACPConfigurationError",
    "ACPErrors",
    "ACPProtocolError",
    "ACPRunnerConfig",
    "ACPService",
    "ACPSessionError",
    "ACPTransportError",
    "SuspendedPermission",
]
