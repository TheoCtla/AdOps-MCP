"""Enregistrement des tools MCP de lecture Google Ads.

Chaque tool est défini dans son propre module et expose trois symboles
publics : ``TOOL_NAME`` (string), ``TOOL_DEFINITION`` (objet ``Tool``
MCP) et ``handler`` (coroutine). Le registre ``_tarmaac_registry``
attaché au server itère simplement sur ``_READ_TOOLS`` pour câbler
chaque tool — ajouter un nouveau tool = créer un module + l'ajouter au
tuple ci-dessous.
"""

from __future__ import annotations

from mcp.server import Server

from google_ads.tools.read import (
    get_adgroup_performance,
    get_ads,
    get_campaign_performance,
    get_daily_performance,
    get_keywords,
    get_negative_keywords,
    get_search_terms,
    list_accounts,
)

_READ_TOOLS = (
    list_accounts,
    get_campaign_performance,
    get_adgroup_performance,
    get_keywords,
    get_daily_performance,
    get_search_terms,
    get_negative_keywords,
    get_ads,
)


def register_read_tools(server: Server) -> None:
    """Attache tous les tools de lecture au registre interne du server MCP.

    Le server expose un unique couple ``list_tools`` / ``call_tool``
    (limitation du SDK), donc on passe par un registre attaché au server
    pour que plusieurs modules coexistent.
    """
    registry = getattr(server, "_tarmaac_registry", None)
    if registry is None:
        registry = {"tools": [], "handlers": {}}
        server._tarmaac_registry = registry  # type: ignore[attr-defined]

    for module in _READ_TOOLS:
        registry["tools"].append(module.TOOL_DEFINITION)
        registry["handlers"][module.TOOL_NAME] = module.handler
