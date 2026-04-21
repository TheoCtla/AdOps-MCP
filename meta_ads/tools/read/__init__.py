"""Enregistrement des tools MCP de lecture Meta Ads."""

from __future__ import annotations

from mcp.server import Server

from meta_ads.tools.read import (
    get_account_info,
    get_ad_creatives,
    get_ad_performance,
    get_adset_performance,
    get_audience_breakdown,
    get_budget_info,
    get_campaign_performance,
    get_creative_asset_details,
    get_custom_audiences,
    get_frequency_data,
    get_hourly_performance,
    get_pixel_events,
    get_placement_performance,
    list_ad_accounts,
)

_META_READ_TOOLS = (
    # --- Core ---
    list_ad_accounts,
    get_campaign_performance,
    get_adset_performance,
    get_ad_performance,
    # --- Analysis ---
    get_audience_breakdown,
    get_custom_audiences,
    get_placement_performance,
    get_hourly_performance,
    get_frequency_data,
    # --- Configuration ---
    get_account_info,
    get_budget_info,
    get_pixel_events,
    get_ad_creatives,
    get_creative_asset_details,
)


def register_meta_read_tools(server: Server) -> None:
    """Attache tous les tools de lecture Meta Ads au registre du server MCP."""
    registry = getattr(server, "_tarmaac_registry", None)
    if registry is None:
        registry = {"tools": [], "handlers": {}}
        server._tarmaac_registry = registry  # type: ignore[attr-defined]

    for module in _META_READ_TOOLS:
        registry["tools"].append(module.TOOL_DEFINITION)
        registry["handlers"][module.TOOL_NAME] = module.handler
