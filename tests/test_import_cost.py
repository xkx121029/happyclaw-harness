"""Guards for the import cost of the package entry points."""

from __future__ import annotations

import subprocess
import sys
from importlib import import_module

import pytest


def _fresh_import_probe(expression: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", expression],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_package_import_does_not_pull_the_agent_stack() -> None:
    """``import happyclaw_harness`` must stay a cheap config-only import.

    The top-level package re-exports ``HarnessAgent`` and friends through PEP 562
    ``__getattr__``; if any of them is imported eagerly, every CLI startup pays
    for the whole LangChain/LangGraph stack (measured at over ten seconds cold).
    """
    out = _fresh_import_probe(
        "import sys, happyclaw_harness;"
        "print('deepagents' in sys.modules, 'langgraph' in sys.modules, 'langchain_core' in sys.modules)"
    )
    assert out == "False False False"


def test_lazy_exports_resolve_to_the_real_objects() -> None:
    import happyclaw_harness

    assert happyclaw_harness.ChatRequest is import_module("happyclaw_harness.request").ChatRequest
    assert happyclaw_harness.HarnessAgent is import_module("happyclaw_harness.agent").HarnessAgent


def test_unknown_attribute_raises_attribute_error() -> None:
    import happyclaw_harness

    with pytest.raises(AttributeError):
        happyclaw_harness.NotARealExport  # noqa: B018
