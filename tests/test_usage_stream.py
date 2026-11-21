"""Usage accounting is correct for every provider shape, and never silently zero."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from happyclaw_harness.agent import HarnessAgent
from happyclaw_harness.budget import BUDGET_EXCEEDED, SessionBudget
from happyclaw_harness.request import ChatRequest
from happyclaw_harness.usage import estimate_usage, merge_usage_reports


def test_openai_gateway_repeating_the_cumulative_total_counts_once() -> None:
    """Gateways that repeat the running total on every chunk must not multiply it."""
    repeated = {"prompt_tokens": 900, "completion_tokens": 10, "total_tokens": 910}

    merged = merge_usage_reports([repeated, repeated, repeated])

    assert merged["input_tokens"] == 900
    assert merged["output_tokens"] == 10
    assert merged["total_tokens"] == 910


def test_anthropic_partial_reports_merge_into_one_call() -> None:
    """``message_start`` carries input, ``message_delta`` carries output."""
    start = {
        "input_tokens": 1_200,
        "output_tokens": 0,
        "input_token_details": {"cache_read": 800, "cache_creation": 250},
    }
    delta = {"input_tokens": 1_200, "output_tokens": 20}

    merged = merge_usage_reports([start, delta])

    assert merged["input_tokens"] == 1_200
    assert merged["uncached_input_tokens"] == 150
    assert merged["cache_read_tokens"] == 800
    assert merged["cache_write_tokens"] == 250
    assert merged["output_tokens"] == 20
    assert merged["total_tokens"] == 1_220


def test_anthropic_cache_fields_survive_a_single_final_report() -> None:
    merged = merge_usage_reports(
        [
            {
                "input_tokens": 500,
                "output_tokens": 40,
                "cache_read_input_tokens": 300,
                "cache_creation_input_tokens": 100,
            }
        ]
    )

    assert merged["cache_read_tokens"] == 300
    assert merged["cache_write_tokens"] == 100
    assert merged["uncached_input_tokens"] == 100


def test_gemini_style_report_on_the_last_chunk_only() -> None:
    merged = merge_usage_reports(
        [{"input_tokens": 700, "output_tokens": 0}, {"input_tokens": 700, "output_tokens": 60}]
    )

    assert merged["total_tokens"] == 760


def test_already_normalized_reports_are_not_renormalized() -> None:
    normalized = {
        "input_tokens": 1_000,
        "uncached_input_tokens": 300,
        "cache_read_tokens": 700,
        "cache_write_tokens": 0,
        "output_tokens": 80,
        "reasoning_tokens": 10,
        "total_tokens": 1_080,
    }

    assert merge_usage_reports([normalized]) == normalized


def test_estimate_is_marked_and_content_based() -> None:
    estimate = estimate_usage([HumanMessage(content="hello there, this is a prompt")], "a short answer")

    assert estimate["estimated"] == 1
    assert estimate["input_tokens"] > 0
    assert estimate["output_tokens"] > 0
    assert estimate["total_tokens"] == estimate["input_tokens"] + estimate["output_tokens"]


def test_estimate_costs_more_for_cjk_text() -> None:
    cjk = estimate_usage([HumanMessage(content="你好" * 50)], "")
    latin = estimate_usage([HumanMessage(content="ab" * 50)], "")

    assert cjk["input_tokens"] > latin["input_tokens"]


class _Proto:
    """Protocol collaborator that reports no usage at all."""

    name = "silent"

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events

    async def stream(self, messages: Any, config: Any, **kwargs: AsyncIterator[Any]) -> AsyncIterator[dict[str, Any]]:
        for event in self.events:
            yield event

    async def call(self, messages: Any, config: Any, **kwargs: Any) -> dict[str, Any]:
        return {"messages": [AIMessage(content="answer from a provider that reports no usage")]}


def _agent(proto: _Proto, budget: SessionBudget | None = None) -> HarnessAgent:
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


@pytest.mark.asyncio
async def test_untracked_session_keeps_the_protocol_stream_untouched() -> None:
    """No budget means no accounting, so no extra events reach the host."""
    proto = _Proto([{"type": "token", "content": "hello"}])
    agent = _agent(proto)

    events = [event async for event in agent.stream(replace(ChatRequest.coerce("hi"), thread_id="plain-1"))]

    assert [event["type"] for event in events] == ["token"]


@pytest.mark.asyncio
async def test_silent_provider_still_reports_estimated_usage() -> None:
    proto = _Proto([{"type": "token", "content": "hello "}, {"type": "token", "content": "world"}])
    agent = _agent(proto, SessionBudget(max_tokens=10_000))

    events = [
        event
        async for event in agent.stream(replace(ChatRequest.coerce("a prompt worth counting"), thread_id="silent-1"))
    ]

    usage_events = [event for event in events if event.get("type") == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["estimated"] is True
    assert usage_events[0]["usage"]["estimated"] == 1
    assert usage_events[0]["usage"]["output_tokens"] > 0
    assert events[-1] is usage_events[0]


@pytest.mark.asyncio
async def test_provider_usage_is_not_replaced_by_the_estimate() -> None:
    proto = _Proto([{"type": "usage", "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}}])
    agent = _agent(proto, SessionBudget(max_tokens=10_000))

    events = [event async for event in agent.stream(replace(ChatRequest.coerce("hi"), thread_id="reported-1"))]

    assert [event["type"] for event in events] == ["usage"]
    assert agent.get_session_usage("reported-1")["total_tokens"] == 10
    assert agent.get_session_usage("reported-1")["estimated_tokens"] == 0


@pytest.mark.asyncio
async def test_estimated_usage_is_counted_against_the_session_ceiling() -> None:
    proto = _Proto([{"type": "token", "content": "x" * 4_000}])
    agent = _agent(proto, SessionBudget(max_tokens=100))

    events = [
        event async for event in agent.stream(replace(ChatRequest.coerce("count this turn"), thread_id="silent-2"))
    ]

    assert events[-1]["type"] == BUDGET_EXCEEDED
    assert events[-1]["usage"]["estimated_tokens"] > 0


@pytest.mark.asyncio
async def test_cancelled_turn_does_not_emit_an_estimate() -> None:
    """A cancelled turn has no complete usage, so it must not report a guess."""

    class _Blocking(_Proto):
        async def stream(self, messages: Any, config: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "content": "partial"}
            await asyncio.Event().wait()

    import asyncio

    agent = _agent(_Blocking([]), SessionBudget(max_tokens=10_000))
    request = replace(ChatRequest.coerce("hi"), thread_id="cancelled-1")
    seen: list[dict[str, Any]] = []

    async def consume() -> None:
        async for event in agent.stream(request):
            seen.append(event)
            if event.get("type") == "token":
                agent.cancel("cancelled-1")

    await asyncio.wait_for(consume(), timeout=10)

    assert [event["type"] for event in seen] == ["token"]
