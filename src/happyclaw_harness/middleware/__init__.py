"""Custom middleware shipped with happyclaw-harness."""

from __future__ import annotations

from happyclaw_harness.middleware.client_tool_search import ClientToolSearchMiddleware
from happyclaw_harness.middleware.conversation_mode import ConversationModeMiddleware
from happyclaw_harness.middleware.filesystem_guard import FilesystemGuardMiddleware
from happyclaw_harness.middleware.mcp_tool_error import McpToolErrorMiddleware
from happyclaw_harness.middleware.media_offload import MediaOffloadMiddleware
from happyclaw_harness.middleware.memory import MemoryMiddleware
from happyclaw_harness.middleware.model_settings import (
    CONFIGURABLE_MAX_INPUT_TOKENS,
    CONFIGURABLE_MODEL_SETTINGS,
    ModelSettingsMiddleware,
)
from happyclaw_harness.middleware.native_tool_search import NativeToolSearchMiddleware
from happyclaw_harness.middleware.peer import PeerAgentMiddleware
from happyclaw_harness.middleware.pii import detect_pii
from happyclaw_harness.middleware.tool_search import ToolSearchMiddleware

__all__ = [
    "CONFIGURABLE_MAX_INPUT_TOKENS",
    "CONFIGURABLE_MODEL_SETTINGS",
    "ClientToolSearchMiddleware",
    "ConversationModeMiddleware",
    "FilesystemGuardMiddleware",
    "McpToolErrorMiddleware",
    "MediaOffloadMiddleware",
    "MemoryMiddleware",
    "ModelSettingsMiddleware",
    "NativeToolSearchMiddleware",
    "PeerAgentMiddleware",
    "ToolSearchMiddleware",
    "detect_pii",
]
