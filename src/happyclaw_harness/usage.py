"""Provider-neutral token usage normalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _detail_total(details: Mapping[str, Any], *names: str) -> int:
    direct = sum(_nonnegative_int(details.get(name)) for name in names)
    prefixed = sum(
        _nonnegative_int(value)
        for key, value in details.items()
        if isinstance(key, str) and any(key.endswith(f"_{name}") for name in names)
    )
    return direct + prefixed


def normalize_usage_metadata(raw: Mapping[str, Any]) -> dict[str, int]:
    """Return disjoint usage buckets from LangChain or provider wire metadata.

    LangChain normalizes ``input_tokens`` to the complete prompt size, including
    cache reads and cache creation.  ``uncached_input_tokens`` therefore removes
    those two subdivisions while ``input_tokens`` remains the context-pressure
    value expected by existing consumers.
    """
    input_details_raw = raw.get("input_token_details") or raw.get("prompt_tokens_details") or {}
    input_details = input_details_raw if isinstance(input_details_raw, Mapping) else {}
    output_details_raw = raw.get("output_token_details") or raw.get("completion_tokens_details") or {}
    output_details = output_details_raw if isinstance(output_details_raw, Mapping) else {}

    cache_read = _nonnegative_int(raw.get("cache_read_tokens")) or _detail_total(
        input_details,
        "cache_read",
        "cached_tokens",
    )
    cache_read = (
        cache_read
        or _nonnegative_int(raw.get("prompt_cache_hit_tokens"))
        # Anthropic's wire field; langchain-anthropic moves it into the details.
        or _nonnegative_int(raw.get("cache_read_input_tokens"))
    )
    cache_write = (
        _nonnegative_int(raw.get("cache_write_tokens"))
        or _detail_total(
            input_details,
            "cache_creation",
            "cache_write",
        )
        or _nonnegative_int(raw.get("cache_creation_input_tokens"))
    )
    reasoning = _nonnegative_int(raw.get("reasoning_tokens")) or _detail_total(
        output_details,
        "reasoning",
        "reasoning_tokens",
    )

    input_tokens = _nonnegative_int(raw.get("input_tokens") or raw.get("prompt_tokens"))
    explicit_uncached = raw.get("uncached_input_tokens")
    if explicit_uncached is not None:
        uncached_input = _nonnegative_int(explicit_uncached)
        if input_tokens == 0:
            input_tokens = uncached_input + cache_read + cache_write
    else:
        uncached_input = max(0, input_tokens - cache_read - cache_write)
    output_tokens = _nonnegative_int(raw.get("output_tokens") or raw.get("completion_tokens"))

    return {
        "input_tokens": input_tokens,
        "uncached_input_tokens": uncached_input,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "total_tokens": input_tokens + output_tokens,
    }


_MERGED_BUCKETS = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens")


def merge_usage_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Merge several reports of one model call into that call's usage.

    Providers spread one call's usage over stream chunks differently:
    OpenAI-compatible gateways repeat the cumulative total on every chunk,
    Anthropic sends input on ``message_start`` and output on
    ``message_delta``, and some local servers report once at the end. A bucket
    of one call never decreases, so the per-bucket maximum is the call's usage
    under all three shapes, while adding the reports would double count the
    first. ``uncached_input_tokens`` is derived afterwards, because each report
    carries its own cache detail. Reports may be raw provider metadata or
    already normalized.
    """
    merged = dict.fromkeys(_MERGED_BUCKETS, 0)
    for report in reports:
        normalized = normalize_usage_metadata(report)
        for bucket in _MERGED_BUCKETS:
            merged[bucket] = max(merged[bucket], _nonnegative_int(normalized.get(bucket)))
    merged["uncached_input_tokens"] = max(
        0, merged["input_tokens"] - merged["cache_read_tokens"] - merged["cache_write_tokens"]
    )
    merged["total_tokens"] = merged["input_tokens"] + merged["output_tokens"]
    return merged


def estimate_usage(messages: Sequence[Any], output_text: str) -> dict[str, int]:
    """Estimate a call's usage when the provider reported none.

    The result carries ``estimated: 1`` so a ledger can tell guessed tokens from
    measured ones. Content-based and therefore approximate (see
    :mod:`happyclaw_harness.context_usage`), but good enough to stop a runaway
    turn instead of letting an unreported provider bill silently.
    """
    from happyclaw_harness.context_usage import _MESSAGE_FRAMING_TOKENS, content_tokens, estimate_tokens

    input_tokens = sum(
        content_tokens(getattr(message, "content", message)) + _MESSAGE_FRAMING_TOKENS for message in messages
    )
    output_tokens = estimate_tokens(output_text)
    return {
        "input_tokens": input_tokens,
        "uncached_input_tokens": input_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,
        "total_tokens": input_tokens + output_tokens,
        "estimated": 1,
    }


__all__ = ["estimate_usage", "merge_usage_reports", "normalize_usage_metadata"]
