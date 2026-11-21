"""Cancel the tool call a cancelled turn is waiting on, not only the stream.

``HarnessAgent.cancel`` stops the graph stream, but a tool that is already
awaiting a subprocess or a slow MCP call keeps running until it finishes on its
own: the process outlives the turn and the coroutine leaks. This module tracks
the running tool call in a scope the turn registers, so cancel reaches the tool
itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from langchain.agents.middleware import AgentMiddleware

T = TypeVar("T")

current_tool_cancel_scope: contextvars.ContextVar[ToolCancelScope | None] = contextvars.ContextVar(
    "happyclaw_tool_cancel_scope",
    default=None,
)


class ToolCancelScope:
    """Hold the asyncio tasks of in-flight tool calls for one streamed turn.

    ``cancel`` is safe to call from another thread, which is how hosts such as
    an ACP server signal cancel.
    """

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._cancelled = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._cancel_now)

    def _cancel_now(self) -> None:
        self._cancelled.set()
        for task in tuple(self._tasks):
            task.cancel()

    async def run(self, factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
        """Run one tool call, cancelling it when the scope is cancelled."""
        task: asyncio.Task[T] = asyncio.create_task(factory())
        self._tasks.add(task)
        try:
            if self.cancelled:
                task.cancel()
            return await task
        finally:
            self._tasks.discard(task)


class ToolCancellationMiddleware(AgentMiddleware):
    """Route every async tool call through the turn's cancel scope."""

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        scope = current_tool_cancel_scope.get()
        if scope is None:
            return await handler(request)

        async def call() -> Any:
            return await handler(request)

        return await scope.run(call)


__all__ = ["ToolCancelScope", "ToolCancellationMiddleware", "current_tool_cancel_scope"]
