"""Enregistrement des tools MCP d'écriture Google Ads.

Ces tools mutent des données via GoogleAdsService.mutate(). Chaque
module expose TOOL_NAME, TOOL_DEFINITION et handler, comme les tools
de lecture.
"""

from __future__ import annotations

from mcp.server import Server

from google_ads.tools.write import (
    add_audience,
    add_keyword,
    add_label,
    add_negative_keyword,
    create_callout,
    create_responsive_search_ad,
    create_sitelink,
    enable_ad,
    enable_ad_group,
    enable_campaign,
    enable_keyword,
    exclude_audience,
    pause_ad,
    pause_ad_group,
    pause_campaign,
    pause_keyword,
    remove_ad,
    remove_keyword,
    remove_negative_keyword,
    update_ad_schedule,
    update_bid_modifier,
    update_campaign_budget,
    update_campaign_targeting,
    update_final_url_suffix,
    update_keyword_bid,
    update_tracking_template,
)

_WRITE_TOOLS = (
    # --- Pause / Enable ---
    pause_campaign,
    enable_campaign,
    pause_ad_group,
    enable_ad_group,
    pause_ad,
    enable_ad,
    pause_keyword,
    enable_keyword,
    # --- Keywords & Negatives ---
    add_negative_keyword,
    remove_negative_keyword,
    add_keyword,
    remove_keyword,
    update_keyword_bid,
    # --- Budget & Targeting ---
    update_campaign_budget,
    update_bid_modifier,
    update_ad_schedule,
    update_campaign_targeting,
    # --- Ads & Assets ---
    create_responsive_search_ad,
    remove_ad,
    create_sitelink,
    create_callout,
    # --- Advanced ---
    add_audience,
    exclude_audience,
    add_label,
    update_tracking_template,
    update_final_url_suffix,
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
