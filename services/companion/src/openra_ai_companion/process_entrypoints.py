from __future__ import annotations

import sys


def game_mcp_command(*arguments: str) -> list[str]:
    """Use the bundled command dispatcher when there is no Python interpreter."""
    prefix = ["game-mcp"] if getattr(sys, "frozen", False) else ["-m", "openra_ai_companion.game_mcp"]
    return [sys.executable, *prefix, *arguments]
