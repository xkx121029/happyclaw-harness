"""Cancel reaches the running tool call, so no tool process or task outlives the turn."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from happyclaw_harness.agent import HarnessAgent
from happyclaw_harness.tool_cancel import ToolCancellationMiddleware, ToolCancelScope, current_tool_cancel_scope


class _Model(FakeMessagesListChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> _Model:
        del tools, kwargs
        return self


def _tool_message(name: str, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": call_id, "type": "tool_call"}])


async def _wait_for(predicate: Any, timeout: float = 20.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            msg = "condition never became true"
            raise AssertionError(msg)
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_cancel_cancels_a_running_tool_and_reaps_its_child_process() -> None:
    started = asyncio.Event()
    state: dict[str, Any] = {}

    async def sleeper() -> str:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
        )
        state["process"] = process
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            process.kill()
            await process.wait()
        return "finished"

    tool = StructuredTool.from_function(
        coroutine=sleeper,
        name="sleeper",
        description="Wait for a minute.",
    )
    graph = create_agent(
        _Model(responses=[_tool_message("sleeper", "call-1"), AIMessage(content="done")]),
        tools=[tool],
        middleware=[ToolCancellationMiddleware()],
        checkpointer=InMemorySaver(),
    )
    scope = ToolCancelScope()
    token = current_tool_cancel_scope.set(scope)
    try:

        async def drive() -> None:
            async for _ in graph.astream(
                {"messages": [HumanMessage("wait")]},
                config={"configurable": {"thread_id": "cancel-tool"}},
            ):
                pass

        task = asyncio.create_task(drive())
        await asyncio.wait_for(started.wait(), timeout=30)
        process = state["process"]
        assert process.returncode is None

        scope.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(task, timeout=30)

        assert process.returncode is not None, "the tool process outlived the cancel"
        await _wait_for(
            lambda: not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        )
    finally:
        current_tool_cancel_scope.reset(token)


@pytest.mark.asyncio
async def test_scope_run_propagates_cancellation_into_the_tool() -> None:
    cleaned = asyncio.Event()

    async def body() -> None:
        try:
            await asyncio.sleep(30)
        finally:
            cleaned.set()

    scope = ToolCancelScope()
    task = asyncio.create_task(scope.run(body))
    await asyncio.sleep(0.1)
    scope.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=10)
    assert cleaned.is_set()
    assert scope.cancelled is True


@pytest.mark.asyncio
async def test_scope_cancel_is_thread_safe() -> None:
    """A host signals cancel from its own thread; the task is still cancelled."""
    import threading

    cleaned = asyncio.Event()

    async def body() -> None:
        try:
            await asyncio.sleep(30)
        finally:
            cleaned.set()

    scope = ToolCancelScope()
    task = asyncio.create_task(scope.run(body))
    await asyncio.sleep(0.1)
    threading.Thread(target=scope.cancel).start()

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=10)
    assert cleaned.is_set()


def test_agent_cancel_cancels_the_registered_scope() -> None:
    agent = object.__new__(HarnessAgent)
    agent._cancel_events = {}
    agent._cancel_scopes = {}

    async def scenario() -> None:
        scope = ToolCancelScope()
        agent._cancel_scopes["thread-1"] = scope
        agent.cancel("thread-1")
        await asyncio.sleep(0)
        assert scope.cancelled is True

    asyncio.run(scenario())
