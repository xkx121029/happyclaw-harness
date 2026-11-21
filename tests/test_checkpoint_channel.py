"""The checkpoint retention reducer channel is resolved lazily and degrades safely."""

from __future__ import annotations

import sys

import pytest


def test_checkpoint_messages_channel_is_built_once() -> None:
    from happyclaw_harness.memory import runtime

    runtime._checkpoint_messages_channel.cache_clear()
    channel = runtime._checkpoint_messages_channel()
    assert channel is not None
    assert runtime._checkpoint_messages_channel() is channel
    runtime._checkpoint_messages_channel.cache_clear()


def test_checkpoint_messages_channel_degrades_when_deepagents_renames_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A renamed private deepagents symbol must not break imports or pruning."""
    from happyclaw_harness.memory import runtime

    monkeypatch.setitem(sys.modules, "deepagents._messages_reducer", None)
    runtime._checkpoint_messages_channel.cache_clear()
    try:
        assert runtime._checkpoint_messages_channel() is None
    finally:
        runtime._checkpoint_messages_channel.cache_clear()
