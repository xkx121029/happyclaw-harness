"""Optional decision-model shortlist for skills, tools, and team members."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from octop_harness.decision.config import DecisionConfig, decision_active

if TYPE_CHECKING:
    from octop_harness.decision.client import (
        DecisionRequestError,
        HttpDecisionClient,
        build_decision_body,
        parse_probabilities,
    )

# The HTTP client pulls httpx (and everything behind it). Config-only callers,
# such as ``HarnessAgentConfig``, must not pay for it, so it resolves lazily.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "DecisionRequestError": ("octop_harness.decision.client", "DecisionRequestError"),
    "HttpDecisionClient": ("octop_harness.decision.client", "HttpDecisionClient"),
    "build_decision_body": ("octop_harness.decision.client", "build_decision_body"),
    "parse_probabilities": ("octop_harness.decision.client", "parse_probabilities"),
}


def __getattr__(name: str) -> object:  # pragma: no cover - thin re-export shim
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    return getattr(import_module(module_name), attr)


__all__ = [
    "DecisionConfig",
    "DecisionRequestError",
    "HttpDecisionClient",
    "build_decision_body",
    "decision_active",
    "parse_probabilities",
]
