"""happyclaw-harness: production-grade Harness Agent on top of LangChain Deep Agents."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from happyclaw_harness._version import __version__
from happyclaw_harness.config import (
    HarnessAgentConfig,
    MediaGenerationConfig,
    MediaProviderConfig,
    ModelConfig,
    ProviderConfig,
)

if TYPE_CHECKING:
    from happyclaw_harness.agent import HarnessAgent
    from happyclaw_harness.init import InitResult, init_workspace
    from happyclaw_harness.manager import AgentEntry, HarnessAgentManager
    from happyclaw_harness.mcp_client import ManagedMCPClient
    from happyclaw_harness.observability.logging import (
        current_log_file,
        default_log_dir,
        setup_logging,
        teardown_logging,
    )
    from happyclaw_harness.protocols.langgraph import AgentEventType
    from happyclaw_harness.providers import ModelPreset, ProviderPreset
    from happyclaw_harness.request import ChatRequest

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "ChatRequest": ("happyclaw_harness.request", "ChatRequest"),
    "ManagedMCPClient": ("happyclaw_harness.mcp_client", "ManagedMCPClient"),
    "AgentEntry": ("happyclaw_harness.manager", "AgentEntry"),
    "HarnessAgentManager": ("happyclaw_harness.manager", "HarnessAgentManager"),
    "ModelPreset": ("happyclaw_harness.providers", "ModelPreset"),
    "ProviderPreset": ("happyclaw_harness.providers", "ProviderPreset"),
    "HarnessAgent": ("happyclaw_harness.agent", "HarnessAgent"),
    "InitResult": ("happyclaw_harness.init", "InitResult"),
    "init_workspace": ("happyclaw_harness.init", "init_workspace"),
    "current_log_file": ("happyclaw_harness.observability.logging", "current_log_file"),
    "default_log_dir": ("happyclaw_harness.observability.logging", "default_log_dir"),
    "setup_logging": ("happyclaw_harness.observability.logging", "setup_logging"),
    "teardown_logging": ("happyclaw_harness.observability.logging", "teardown_logging"),
    "ChatProtocol": ("happyclaw_harness.protocols", "ChatProtocol"),
    "register_protocol": ("happyclaw_harness.protocols", "register_protocol"),
    "resolve_protocol": ("happyclaw_harness.protocols", "resolve_protocol"),
    "AgentEventType": ("happyclaw_harness.protocols.langgraph", "AgentEventType"),
    "SecurityPolicy": ("happyclaw_harness.security.models", "SecurityPolicy"),
}


def __getattr__(name: str) -> object:  # pragma: no cover - thin re-export shim
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    return getattr(import_module(module_name), attr)


__all__ = [
    "AgentEntry",
    "AgentEventType",
    "ChatProtocol",
    "ChatRequest",
    "HarnessAgent",
    "HarnessAgentConfig",
    "HarnessAgentManager",
    "InitResult",
    "ManagedMCPClient",
    "MediaGenerationConfig",
    "MediaProviderConfig",
    "ModelConfig",
    "ModelPreset",
    "ProviderConfig",
    "ProviderPreset",
    "SecurityPolicy",
    "__version__",
    "current_log_file",
    "default_log_dir",
    "init_workspace",
    "register_protocol",
    "resolve_protocol",
    "setup_logging",
    "teardown_logging",
]
