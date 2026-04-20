"""Enregistrement des tools MCP d'écriture Google Ads.

Ces tools mutent des données via GoogleAdsService.mutate(). Chaque
module expose TOOL_NAME, TOOL_DEFINITION et handler, comme les tools
de lecture.
"""

from __future__ import annotations

from mcp.server import Server

from google_ads.tools.write import (
    enable_ad,
    enable_ad_group,
    enable_campaign,
    enable_keyword,
    pause_ad,
    pause_ad_group,
    pause_campaign,
    pause_keyword,
)

_WRITE_TOOLS = (
    pause_campaign,
    enable_campaign,
    pause_ad_group,
    enable_ad_group,
    pause_ad,
    enable_ad,
    pause_keyword,
    enable_keyword,
)


def register_write_tools(server: Server) -> None:
    """Attache tous les tools d'écriture au registre interne du server MCP."""
    registry = getattr(server, "_tarmaac_registry", None)
    if registry is None:
        registry = {"tools": [], "handlers": {}}
        server._tarmaac_registry = registry  # type: ignore[attr-defined]

    for module in _WRITE_TOOLS:
        registry["tools"].append(module.TOOL_DEFINITION)
        registry["handlers"][module.TOOL_NAME] = module.handler
