"""The LangGraph v3 checkpoint-lease adapter degrades instead of raising."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest

from happyclaw_harness.protocols.langgraph import LangGraphProtocol
from happyclaw_harness.protocols.langgraph_stream_compat import attach_checkpoint_guard, warn_unguarded


class _Source:
    """Stand-in for LangGraph's internal event iterator."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.closed = False

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for item in self.items:
            yield item
        self.closed = True


class _MutableStream:
    """A v3-shaped stream object whose seam is an ordinary attribute."""

    def __init__(self, items: list[Any]) -> None:
        self._graph_aiter = _Source(items)

    async def collect(self) -> list[Any]:
        return [item async for item in self._graph_aiter]


class _ReadOnlyStream:
    """A v3-shaped stream whose seam is a property without a setter."""

    def __init__(self, items: list[Any]) -> None:
        self._source = _Source(items)

    @property
    def _graph_aiter(self) -> _Source:
        return self._source


class _IgnoringStream:
    """A seam whose setter accepts writes and drops them."""

    def __init__(self, items: list[Any]) -> None:
        self._source = _Source(items)

    @property
    def _graph_aiter(self) -> _Source:
        return self._source

    @_graph_aiter.setter
    def _graph_aiter(self, value: Any) -> None:
        return None


class _NoSeamStream:
    """A future v3 stream that no longer exposes the iterator at all."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items


async def _tagging_wrap(source: AsyncIterator[Any]) -> AsyncIterator[Any]:
    async for item in source:
        yield f"guarded:{item}"


def _wrap(source: AsyncIterator[Any]) -> AsyncIterator[Any]:
    return _tagging_wrap(source)


@pytest.mark.asyncio
async def test_present_seam_is_wrapped_and_used() -> None:
    stream = _MutableStream([1, 2])

    result = attach_checkpoint_guard(stream, _wrap)

    assert result.guarded is True
    assert result.reason == ""
    assert await stream.collect() == ["guarded:1", "guarded:2"]


@pytest.mark.asyncio
async def test_missing_seam_returns_the_public_stream_untouched(caplog: pytest.LogCaptureFixture) -> None:
    stream = _NoSeamStream([1, 2])

    with caplog.at_level(logging.WARNING):
        result = attach_checkpoint_guard(stream, _wrap)
        warn_unguarded(result) if not result.guarded else None

    assert result.guarded is False
    assert result.stream is stream
    assert "no _graph_aiter" in result.reason
    assert "still works" in caplog.text


@pytest.mark.asyncio
async def test_read_only_seam_degrades_without_corrupting_the_stream() -> None:
    stream = _ReadOnlyStream([1, 2])

    result = attach_checkpoint_guard(stream, _wrap)

    assert result.guarded is False
    assert "read-only" in result.reason
    assert [item async for item in stream._graph_aiter] == [1, 2]


@pytest.mark.asyncio
async def test_ignored_assignment_restores_the_original_iterator() -> None:
    stream = _IgnoringStream([1, 2])

    result = attach_checkpoint_guard(stream, _wrap)

    assert result.guarded is False
    assert "ignored the assignment" in result.reason
    assert [item async for item in stream._graph_aiter] == [1, 2]


@pytest.mark.asyncio
async def test_non_iterator_seam_is_rejected() -> None:
    class _WeirdStream:
        _graph_aiter = 42

    result = attach_checkpoint_guard(_WeirdStream(), _wrap)

    assert result.guarded is False
    assert "not an async iterator" in result.reason


class _Checkpointer:
    def checkpoint_activity(self, key: str) -> Any:  # pragma: no cover - signature probe only
        return None


class _FutureGraph:
    """A v3 graph whose event stream no longer exposes the internal seam."""

    checkpointer = _Checkpointer()

    async def astream_events(self, *args: Any, **kwargs: Any) -> Any:
        return _NoSeamStream([])


@pytest.mark.asyncio
async def test_protocol_returns_the_stream_instead_of_raising(caplog: pytest.LogCaptureFixture) -> None:
    protocol = LangGraphProtocol(graph=_FutureGraph())

    with caplog.at_level(logging.WARNING):
        stream = await protocol.stream_events([], {"configurable": {"thread_id": "t"}})

    assert isinstance(stream, _NoSeamStream)
    assert "checkpoint activity lease not attached" in caplog.text


class _SeamGraph(_FutureGraph):
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    async def astream_events(self, *args: Any, **kwargs: Any) -> Any:
        return self._stream


@pytest.mark.asyncio
async def test_protocol_wraps_the_seam_when_it_exists() -> None:
    source = _Source([1])
    stream = _MutableStream([])
    stream._graph_aiter = source
    protocol = LangGraphProtocol(graph=_SeamGraph(stream))

    returned = await protocol.stream_events([], {"configurable": {"thread_id": "t"}})

    assert returned is stream
    # The lease wrapper replaced the internal iterator; the object itself stays
    # the native LangGraph stream, so output() and projections still work.
    assert stream._graph_aiter is not source
