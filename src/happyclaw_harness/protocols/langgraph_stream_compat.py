"""Attach the checkpoint lease to a LangGraph v3 event stream without trusting its internals.

LangGraph's v3 ``astream_events`` object pumps a single internal iterator, and
the checkpoint-activity lease has to wrap that iterator so the lease is held
through the final flush even when a consumer uses ``output()`` or a subgraph
projection. The attribution-free public API does not expose that seam, so the
adapter below probes for it, verifies the assignment actually took effect, and
degrades to the unguarded public stream with a warning instead of raising when a
LangGraph release renames or removes it.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_INTERNAL_ITERATOR_ATTR = "_graph_aiter"


@dataclass(frozen=True)
class GuardedStream:
    """The stream to return plus whether the checkpoint lease was attached."""

    stream: Any
    guarded: bool
    reason: str = ""


def attach_checkpoint_guard(
    stream: Any,
    wrap: Callable[[AsyncIterator[Any]], AsyncIterator[Any]],
) -> GuardedStream:
    """Wrap the stream's internal iterator with *wrap* when that seam exists.

    ``wrap`` builds the guarded iterator from the original one. Any probe
    failure returns the stream untouched and says why, so a LangGraph upgrade
    costs checkpoint-lease coverage on this path rather than a broken agent.
    """
    source = getattr(stream, _INTERNAL_ITERATOR_ATTR, None)
    if source is None:
        return GuardedStream(stream, False, f"stream has no {_INTERNAL_ITERATOR_ATTR}")
    if not hasattr(source, "__aiter__"):
        return GuardedStream(stream, False, f"{_INTERNAL_ITERATOR_ATTR} is not an async iterator")
    guarded = wrap(source)
    try:
        setattr(stream, _INTERNAL_ITERATOR_ATTR, guarded)
    except (AttributeError, TypeError) as exc:
        return GuardedStream(stream, False, f"{_INTERNAL_ITERATOR_ATTR} is read-only: {exc}")
    if getattr(stream, _INTERNAL_ITERATOR_ATTR, None) is not guarded:
        with contextlib.suppress(AttributeError, TypeError):
            setattr(stream, _INTERNAL_ITERATOR_ATTR, source)
        return GuardedStream(stream, False, f"{_INTERNAL_ITERATOR_ATTR} ignored the assignment")
    return GuardedStream(stream, True)


def warn_unguarded(guarded: GuardedStream) -> None:
    """Log the one-line degradation notice once per call site."""
    logger.warning(
        "checkpoint activity lease not attached to the LangGraph v3 event stream (%s); "
        "the stream still works, but its final checkpoint flush is not covered by the lease",
        guarded.reason,
    )


__all__ = ["GuardedStream", "attach_checkpoint_guard", "warn_unguarded"]
