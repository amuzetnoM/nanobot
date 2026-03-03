"""
nanobots - Fire-and-forget micro-agents for AI systems.
Spawn, execute, self-destruct.
"""

__version__ = "0.1.1"

from nanobots.core import spawn, spawn_async, Nanobot, NanobotResult
from nanobots.registry import list_spaces, list_bots, get_bot, get_bot_meta

__all__ = [
    "spawn",
    "spawn_async",
    "Nanobot",
    "NanobotResult",
    "list_spaces",
    "list_bots",
    "get_bot",
    "get_bot_meta",
    "__version__",
]
