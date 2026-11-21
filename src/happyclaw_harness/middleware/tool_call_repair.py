"""Ask the model once to fix tool-call arguments that were not valid JSON.

A provider that truncates or corrupts a tool-call delta leaves the message with
``invalid_tool_calls``, or with ``tool_calls`` whose ``args`` are still a raw
string. Neither can execute, so today's turn ends with nothing done. This
middleware spends one extra model call on a written repair instruction and, when
that also fails, ends the turn with a structured error message instead of an
exception.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

TOOL_CALL_ERROR_KEY = "harness_tool_call_error"
"""``additional_kwargs`` key of the message that reports an unrepaired call."""

_REPAIR_INSTRUCTION = (
    "Your previous response contained tool calls whose arguments were not valid JSON, "
    "so none of them ran. Re-emit those calls now: keep the same tool names and call "
    "ids, and send the arguments of each call as a single JSON object. Emit no prose."
)
_MAX_RAW_ARG_CHARS = 2000


def _raw_args_text(args: Any) -> str:
    if isinstance(args, str):
        text = args
    elif isinstance(args, Mapping):
        text = json.dumps(args, ensure_ascii=False)
    else:
        text = str(args)
    if len(text) > _MAX_RAW_ARG_CHARS:
        return f"{text[:_MAX_RAW_ARG_CHARS]}…(truncated)"
    return text


def broken_tool_calls(message: Any) -> list[dict[str, str]]:
    """Return the malformed tool calls carried by one AI message.

    Each entry names the tool, its call id, the raw arguments and the parse
    error, which is everything the model needs to repair the call.
    """
    return [
        {
            "name": str(call.get("name") or ""),
            "id": str(call.get("id") or ""),
            "args": _raw_args_text(call.get("args")),
            "error": str(call.get("error") or "arguments were not a JSON object"),
        }
        for call in getattr(message, "invalid_tool_calls", None) or []
    ]


def _repair_prompt(messages: Sequence[Any], broken: list[dict[str, str]]) -> list[Any]:
    details = "\n".join(
        f"- tool {call['name'] or 'unknown'} (call id {call['id'] or 'unset'}): "
        f"{call['error']}. Arguments received:\n{call['args']}"
        for call in broken
    )
    return [*messages, HumanMessage(content=f"{_REPAIR_INSTRUCTION}\n\n{details}")]


def _structured_failure(broken: list[dict[str, str]]) -> AIMessage:
    names = ", ".join(sorted({call["name"] or "unknown tool" for call in broken}))
    return AIMessage(
        content=(
            "The model returned tool-call arguments that are not valid JSON and the repair attempt did not "
            f"produce a usable call either ({names}), so nothing was executed and no changes were made. "
            "Retry the request, or switch to a model with more reliable tool calling for this task."
        ),
        additional_kwargs={
            TOOL_CALL_ERROR_KEY: {"reason": "invalid_tool_call_arguments", "tool_calls": broken},
        },
    )


@dataclass
class _Repair:
    """One turn's repair state: the history to re-ask from and the calls to fix."""

    history: list[Any]
    pending: Any
    broken: list[dict[str, str]]
    attempts: int = field(default=0)

    def prompt(self) -> list[Any]:
        return _repair_prompt([*self.history, self.pending], self.broken)

    def accept(self, candidate: Any) -> ModelResponse[Any] | None:
        """Return the repaired response, or record the failure and continue."""
        still_broken = broken_tool_calls(candidate)
        if not still_broken and getattr(candidate, "tool_calls", None):
            return ModelResponse(result=[*self.history, candidate])
        self.pending = candidate
        self.broken = still_broken or self.broken
        return None

    def failed(self) -> ModelResponse[Any]:
        logger.warning(
            "tool-call repair failed for %s after %d attempt(s)",
            ", ".join(call["name"] or "unknown" for call in self.broken),
            self.attempts,
        )
        return ModelResponse(result=[*self.history, _structured_failure(self.broken)])


def _start(response: ModelResponse[Any]) -> _Repair | None:
    """Return repair state when the response carries a malformed tool call."""
    last_ai = next((message for message in reversed(response.result) if getattr(message, "type", None) == "ai"), None)
    broken = broken_tool_calls(last_ai)
    if last_ai is None or not broken:
        return None
    return _Repair(history=list(response.result[:-1]), pending=last_ai, broken=broken)


class ToolCallRepairMiddleware(AgentMiddleware):
    """Repair malformed tool-call JSON once, then end the turn with a structured error.

    ``max_attempts`` counts repair model calls, not total model calls: ``0``
    disables the retry and only converts the failure into a structured message.
    """

    def __init__(self, *, max_attempts: int = 1, enabled: bool = True) -> None:
        super().__init__()
        self.max_attempts = max(0, int(max_attempts))
        self.enabled = enabled

    @staticmethod
    def _model_for_repair(request: ModelRequest[Any]) -> Any:
        model = request.model
        bind = getattr(model, "bind_tools", None)
        if request.tools and callable(bind):
            try:
                return bind(request.tools)
            except (TypeError, ValueError, AttributeError):
                logger.debug("bind_tools failed during tool-call repair", exc_info=True)
        return model

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        response = handler(request)
        state = _start(response) if self.enabled else None
        if state is None:
            return response
        model = self._model_for_repair(request)
        while state.attempts < self.max_attempts:
            state.attempts += 1
            try:
                candidate = model.invoke(state.prompt())
            except Exception:  # a failed repair call degrades to the structured error
                logger.warning("tool-call repair call failed", exc_info=True)
                break
            if (repaired := state.accept(candidate)) is not None:
                return repaired
        return state.failed()

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        response = await handler(request)
        state = _start(response) if self.enabled else None
        if state is None:
            return response
        model = self._model_for_repair(request)
        while state.attempts < self.max_attempts:
            state.attempts += 1
            try:
                candidate = await model.ainvoke(state.prompt())
            except Exception:  # a failed repair call degrades to the structured error
                logger.warning("tool-call repair call failed", exc_info=True)
                break
            if (repaired := state.accept(candidate)) is not None:
                return repaired
        return state.failed()


__all__ = ["TOOL_CALL_ERROR_KEY", "ToolCallRepairMiddleware", "broken_tool_calls"]
