"""ToolCallRepairMiddleware: one repair attempt for malformed tool-call JSON."""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from happyclaw_harness.middleware.tool_call_repair import (
    TOOL_CALL_ERROR_KEY,
    ToolCallRepairMiddleware,
    broken_tool_calls,
)


def _echo_tool(calls: list[str]) -> StructuredTool:
    def echo(text: str) -> str:
        calls.append(text)
        return f"echoed:{text}"

    return StructuredTool.from_function(echo, name="echo", description="Echo the text back.")


class _RecordingModel(FakeMessagesListChatModel):
    """A real chat model that remembers every prompt it was asked."""

    seen: list[list[BaseMessage]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> _RecordingModel:
        del tools, kwargs
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
        return self._generate(messages, stop, run_manager, **kwargs)


def _malformed() -> AIMessage:
    return AIMessage(
        content="",
        invalid_tool_calls=[{"name": "echo", "args": '{"text": hi there}', "id": "call-1", "error": "Expecting value"}],
    )


def _valid_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "echo", "args": {"text": "hi there"}, "id": "call-1", "type": "tool_call"}],
    )


def _graph(model: _RecordingModel, calls: list[str], attempts: int = 1) -> Any:
    return create_agent(
        model,
        tools=[_echo_tool(calls)],
        middleware=[ToolCallRepairMiddleware(max_attempts=attempts)],
        checkpointer=InMemorySaver(),
    )


def _repair_prompts(model: _RecordingModel) -> list[str]:
    prompts = [
        "\n".join(str(message.content) for message in prompt if isinstance(message, HumanMessage))
        for prompt in model.seen
    ]
    return [prompt for prompt in prompts if "not valid JSON" in prompt]


def test_broken_tool_calls_reads_invalid_calls() -> None:
    assert broken_tool_calls(_malformed()) == [
        {
            "name": "echo",
            "id": "call-1",
            "args": '{"text": hi there}',
            "error": "Expecting value",
        }
    ]
    assert broken_tool_calls(AIMessage(content="plain reply")) == []


def test_valid_tool_call_never_reaches_the_repair_path() -> None:
    calls: list[str] = []
    model = _RecordingModel(responses=[_valid_call(), AIMessage(content="done")])
    result = _graph(model, calls).invoke(
        {"messages": [HumanMessage("say hi")]},
        config={"configurable": {"thread_id": "valid"}},
    )

    assert calls == ["hi there"]
    assert len(model.seen) == 2
    assert all("not valid JSON" not in str(message.content) for prompt in model.seen for message in prompt)
    assert result["messages"][-1].content == "done"


def test_bad_json_triggers_exactly_one_repair() -> None:
    calls: list[str] = []
    model = _RecordingModel(responses=[_malformed(), _valid_call(), AIMessage(content="done")])
    result = _graph(model, calls).invoke(
        {"messages": [HumanMessage("say hi")]},
        config={"configurable": {"thread_id": "repair"}},
    )

    assert len(model.seen) == 3
    prompts = _repair_prompts(model)
    assert len(prompts) == 1
    assert '{"text": hi there}' in prompts[0]
    assert "Expecting value" in prompts[0]
    assert calls == ["hi there"]
    assert result["messages"][-1].content == "done"


@pytest.mark.asyncio
async def test_bad_json_triggers_one_repair_when_streaming() -> None:
    calls: list[str] = []
    model = _RecordingModel(responses=[_malformed(), _valid_call(), AIMessage(content="done")])
    events = [
        chunk
        async for chunk in _graph(model, calls).astream(
            {"messages": [HumanMessage("say hi")]},
            config={"configurable": {"thread_id": "repair-async"}},
        )
    ]

    assert events
    assert len(model.seen) == 3
    assert calls == ["hi there"]


def test_second_failure_returns_a_structured_error_instead_of_raising() -> None:
    calls: list[str] = []
    model = _RecordingModel(responses=[_malformed(), _malformed(), AIMessage(content="never reached")])
    result = _graph(model, calls).invoke(
        {"messages": [HumanMessage("say hi")]},
        config={"configurable": {"thread_id": "twice"}},
    )

    final = result["messages"][-1]
    assert calls == []
    assert len(model.seen) == 2
    assert "not valid JSON" in final.content
    assert final.tool_calls == []
    assert final.invalid_tool_calls == []
    error = final.additional_kwargs[TOOL_CALL_ERROR_KEY]
    assert error["reason"] == "invalid_tool_call_arguments"
    assert error["tool_calls"][0]["name"] == "echo"


def test_zero_attempts_reports_the_structured_error_immediately() -> None:
    calls: list[str] = []
    model = _RecordingModel(responses=[_malformed(), AIMessage(content="unused")])
    result = _graph(model, calls, attempts=0).invoke(
        {"messages": [HumanMessage("say hi")]},
        config={"configurable": {"thread_id": "no-retry"}},
    )

    final = result["messages"][-1]
    assert len(model.seen) == 1
    assert TOOL_CALL_ERROR_KEY in final.additional_kwargs
    assert calls == []
