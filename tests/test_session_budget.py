"""Per-session token and cost ceilings stop a turn gracefully and say why."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from happyclaw_harness.agent import HarnessAgent
from happyclaw_harness.budget import (
    BUDGET_EXCEEDED,
    EXCEEDED_COST,
    EXCEEDED_TOKENS,
    SessionBudget,
    SessionUsage,
)
from happyclaw_harness.request import ChatRequest


class _Proto:
    """Protocol collaborator that replays a scripted event list."""

    name = "fake"

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.calls = 0

    async def stream(self, messages: Any, config: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls += 1
        for event in self.events:
            yield event

    async def call(self, messages: Any, config: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {"messages": self.events}


def _agent(proto: _Proto, budget: SessionBudget | None) -> HarnessAgent:
    agent = object.__new__(HarnessAgent)
    agent._cancel_events = {}
    agent._cancel_scopes = {}
    agent._hitl_resume_configs = {}
    agent._thread_models = {}
    agent._agent_id = None
    agent._session_budget = budget
    agent._session_usage = {}
    agent._lifecycle_lock = threading.Lock()
    agent._in_flight = 0
    agent._close_pending = False
    agent._config = SimpleNamespace(pick_default_model_ref=lambda: "test/model")  # type: ignore[assignment]
    agent._get_protocol = lambda name: proto  # type: ignore[method-assign]
    return agent


def _usage(input_tokens: int, output_tokens: int = 0, **extra: Any) -> dict[str, Any]:
    return {
        "type": "usage",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        **extra,
    }


async def _drain(agent: HarnessAgent, thread_id: str = "session-1") -> list[dict[str, Any]]:
    request = replace(ChatRequest.coerce("hello"), thread_id=thread_id)
    return [event async for event in agent.stream(request)]


@pytest.mark.asyncio
async def test_token_ceiling_stops_the_stream_and_reports_the_reason() -> None:
    proto = _Proto([_usage(60), {"type": "token", "content": "a"}, _usage(60), {"type": "token", "content": "never"}])
    agent = _agent(proto, SessionBudget(max_tokens=100))

    events = await _drain(agent)

    assert [event["type"] for event in events] == ["usage", "token", "usage", BUDGET_EXCEEDED]
    assert events[-1]["reason"] == EXCEEDED_TOKENS
    assert events[-1]["usage"]["total_tokens"] == 120
    assert events[-1]["limit"]["max_tokens"] == 100
    assert agent.get_session_usage("session-1")["total_tokens"] == 120


@pytest.mark.asyncio
async def test_turn_inside_the_ceiling_is_untouched() -> None:
    proto = _Proto([_usage(10, 5), {"type": "token", "content": "answer"}])
    agent = _agent(proto, SessionBudget(max_tokens=1_000))

    events = await _drain(agent)

    assert [event["type"] for event in events] == ["usage", "token"]
    assert agent.get_session_usage("session-1") == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cost_usd": 0.0,
        "estimated_tokens": 0,
        "unpriced_tokens": 15,
    }


@pytest.mark.asyncio
async def test_exhausted_session_refuses_the_next_turn_without_calling_the_model() -> None:
    proto = _Proto([_usage(200)])
    agent = _agent(proto, SessionBudget(max_tokens=100))
    await _drain(agent)
    assert proto.calls == 1

    events = await _drain(agent)

    assert proto.calls == 1
    assert [event["type"] for event in events] == [BUDGET_EXCEEDED]
    assert events[0]["reason"] == EXCEEDED_TOKENS


@pytest.mark.asyncio
async def test_cost_ceiling_uses_the_configured_price() -> None:
    # 1000 input tokens at $1/M plus 1000 output at $2/M is $0.003.
    proto = _Proto([_usage(1_000, 1_000)])
    agent = _agent(proto, SessionBudget(max_cost_usd=0.002, price_per_million=(1.0, 2.0)))

    events = await _drain(agent)

    assert events[-1]["type"] == BUDGET_EXCEEDED
    assert events[-1]["reason"] == EXCEEDED_COST
    assert events[-1]["usage"]["cost_usd"] == pytest.approx(0.003)
    assert events[-1]["usage"]["unpriced_tokens"] == 0


@pytest.mark.asyncio
async def test_cost_ceiling_without_a_price_never_aborts() -> None:
    proto = _Proto([_usage(10_000_000)])
    agent = _agent(proto, SessionBudget(max_cost_usd=0.001))

    events = await _drain(agent)

    assert [event["type"] for event in events] == ["usage"]
    assert agent.get_session_usage("session-1")["unpriced_tokens"] == 10_000_000


@pytest.mark.asyncio
async def test_non_streamed_call_reports_the_ceiling_in_its_result() -> None:
    proto = _Proto(
        [AIMessage(content="done", usage_metadata={"input_tokens": 900, "output_tokens": 100, "total_tokens": 1_000})]
    )
    agent = _agent(proto, SessionBudget(max_tokens=500))

    result = await agent.call(replace(ChatRequest.coerce("hello"), thread_id="session-2"))

    assert result[BUDGET_EXCEEDED]["reason"] == EXCEEDED_TOKENS
    assert result[BUDGET_EXCEEDED]["stop"] == "graceful"
    assert result["messages"][-1].content == "done"


@pytest.mark.asyncio
async def test_reset_starts_a_fresh_window() -> None:
    proto = _Proto([_usage(200)])
    agent = _agent(proto, SessionBudget(max_tokens=100))
    await _drain(agent)
    agent.reset_session_usage("session-1")

    events = await _drain(agent)

    assert proto.calls == 2
    assert events[0]["type"] == "usage"
    assert agent.get_session_usage("session-1")["total_tokens"] == 200


def test_usage_records_estimated_tokens_separately() -> None:
    usage = SessionUsage()
    usage.record({"input_tokens": 100, "output_tokens": 20, "estimated": 1})
    usage.record({"input_tokens": 30, "output_tokens": 5})

    assert usage.to_dict() == {
        "input_tokens": 130,
        "output_tokens": 25,
        "total_tokens": 155,
        "cost_usd": 0.0,
        "estimated_tokens": 120,
        "unpriced_tokens": 155,
    }


def test_estimated_usage_counts_toward_the_token_ceiling() -> None:
    usage = SessionUsage()
    budget = SessionBudget(max_tokens=100)
    usage.record({"input_tokens": 80, "output_tokens": 30, "estimated": 1}, budget)
    assert usage.exceeded(budget) == EXCEEDED_TOKENS


def test_session_budget_must_be_opt_in() -> None:
    assert SessionBudget().active is False
    assert SessionBudget(max_tokens=0, max_cost_usd=0.0).active is False
    assert SessionBudget(max_tokens=1).active is True


def test_human_message_is_not_mistaken_for_usage() -> None:
    proto = _Proto([HumanMessage(content="hello")])
    agent = _agent(proto, SessionBudget(max_tokens=10))
    assert agent.get_session_usage("nobody")["total_tokens"] == 0
