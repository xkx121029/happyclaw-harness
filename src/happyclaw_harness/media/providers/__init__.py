"""Built-in media generation provider adapters."""

from happyclaw_harness.media.providers.dashscope import DashScopeMediaProvider
from happyclaw_harness.media.providers.minimax import MiniMaxMediaProvider
from happyclaw_harness.media.providers.volcengine import VolcengineMediaProvider

__all__ = ["DashScopeMediaProvider", "MiniMaxMediaProvider", "VolcengineMediaProvider"]
