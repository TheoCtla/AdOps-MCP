"""Enregistrement des tools MCP d'écriture Meta Ads."""

from __future__ import annotations

from mcp.server import Server

from meta_ads.tools.write import (
    create_ad,
    create_adset,
    create_campaign,
    create_custom_audience,
    create_lookalike_audience,
    duplicate_ad,
    duplicate_adset,
    enable_ad,
    enable_adset,
    enable_campaign,
    pause_ad,
    pause_adset,
    pause_campaign,
    update_ad_creative,
    update_ad_name,
    update_ad_url,
    update_ad_utm,
    update_adset_bid,
    update_adset_budget,
    update_adset_placements,
    update_adset_schedule,
    update_adset_targeting,
    update_campaign_budget,
    upload_image,
)

_META_WRITE_TOOLS = (
    # --- Pause / Enable ---
    pause_campaign,
    enable_campaign,
    pause_adset,
    enable_adset,
    pause_ad,
    enable_ad,
    # --- Budgets & Copy ---
    update_campaign_budget,
    update_adset_budget,
    update_ad_creative,
    update_ad_url,
    update_ad_utm,
    # --- Create & Duplicate ---
    create_campaign,
    create_adset,
    create_ad,
    duplicate_ad,
    duplicate_adset,
    # --- Targeting & Config ---
    update_adset_targeting,
    update_adset_placements,
    update_adset_schedule,
    update_adset_bid,
    update_ad_name,
    # --- Assets & Audiences ---
    upload_image,
    create_custom_audience,
    create_lookalike_audience,
)


def register_meta_write_tools(server: Server) -> None:
    """Attache tous les tools d'écriture Meta Ads au registre du server MCP."""
    registry = getattr(server, "_tarmaac_registry", None)
    if registry is None:
        registry = {"tools": [], "handlers": {}}
        server._tarmaac_registry = registry  # type: ignore[attr-defined]

    for module in _META_WRITE_TOOLS:
        registry["tools"].append(module.TOOL_DEFINITION)
        registry["handlers"][module.TOOL_NAME] = module.handler
