"""Per-session token and cost ceilings with a graceful stop.

A single-user deployment often runs unattended: a scheduled turn, a long tool
loop, a model that keeps re-planning. Without a ceiling the first sign of
trouble is the bill. :class:`SessionBudget` caps a thread's accumulated usage
and :class:`SessionUsage` records what the thread has spent so far, so the
harness can stop a turn between model calls and say why it stopped.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

BUDGET_EXCEEDED = "budget_exceeded"
"""Stream event type, and ``call()`` result key, reporting a stopped turn."""

EXCEEDED_TOKENS = "max_session_tokens"
EXCEEDED_COST = "max_session_cost_usd"


@dataclass(frozen=True)
class SessionBudget:
    """Ceilings for one session (one ``thread_id``).

    ``None`` or ``0`` disables a ceiling. A cost ceiling needs
    ``price_per_million``: without a price the cost ceiling is skipped and the
    usage is reported as unpriced, because guessing a provider's price would
    abort the wrong sessions.
    """

    max_tokens: int | None = None
    max_cost_usd: float | None = None
    price_per_million: tuple[float, float] | None = None

    @property
    def active(self) -> bool:
        return bool(self.max_tokens) or bool(self.max_cost_usd)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "price_per_million": list(self.price_per_million) if self.price_per_million else None,
        }


@dataclass
class SessionUsage:
    """Accumulated usage of one session, including how much of it was priced."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    estimated_tokens: int = 0
    unpriced_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def record(self, usage: Mapping[str, Any], budget: SessionBudget | None = None) -> None:
        """Add one normalized usage report (see :mod:`happyclaw_harness.usage`)."""
        input_tokens = _count(usage.get("input_tokens"))
        output_tokens = _count(usage.get("output_tokens"))
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if usage.get("estimated"):
            self.estimated_tokens += input_tokens + output_tokens
        price = budget.price_per_million if budget is not None else None
        if price is None:
            self.unpriced_tokens += input_tokens + output_tokens
            return
        input_price, output_price = price
        self.cost_usd += (input_tokens * input_price + output_tokens * output_price) / 1_000_000

    def exceeded(self, budget: SessionBudget) -> str | None:
        """Return the ceiling this session crossed, if any."""
        if budget.max_tokens and self.total_tokens >= budget.max_tokens:
            return EXCEEDED_TOKENS
        if budget.max_cost_usd and self.cost_usd >= budget.max_cost_usd:
            return EXCEEDED_COST
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "estimated_tokens": self.estimated_tokens,
            "unpriced_tokens": self.unpriced_tokens,
        }


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def budget_exceeded_event(reason: str, budget: SessionBudget, usage: SessionUsage) -> dict[str, Any]:
    """The event a streamed turn ends with when it hits a ceiling."""
    return {
        "type": BUDGET_EXCEEDED,
        "reason": reason,
        "limit": budget.to_dict(),
        "usage": usage.to_dict(),
        "stop": "graceful",
    }


__all__ = [
    "BUDGET_EXCEEDED",
    "EXCEEDED_COST",
    "EXCEEDED_TOKENS",
    "SessionBudget",
    "SessionUsage",
    "budget_exceeded_event",
]
