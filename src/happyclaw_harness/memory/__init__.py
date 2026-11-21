"""Memory adapter helpers for happyclaw-harness.

The public surface includes :class:`MemoryRuntime`, which wires
:class:`octop_memory.Memory` / :class:`octop_memory.MemoryService` into the
agent, and :func:`checkpoint_activity`, which coordinates host graph operations
with PostgreSQL checkpoint maintenance.

:class:`happyclaw_harness.memory.llm_client.HarnessAgentLLMClient` is an internal
adapter used by :class:`MemoryRuntime` to expose the agent's
:class:`~happyclaw_harness.llm.factory.ChatModelFactory` to octop-memory's
extractor / promotion / page-regeneration paths via the
:class:`octop_memory.ports.llm.LLMClient` protocol. It is intentionally not
re-exported here: callers who need a custom LLM client should implement the
``LLMClient`` protocol directly rather than subclassing or constructing this
adapter themselves.
"""

from __future__ import annotations

from happyclaw_harness.memory.checkpoint_activity import checkpoint_activity
from happyclaw_harness.memory.runtime import MemoryRuntime

__all__ = ["MemoryRuntime", "checkpoint_activity"]
