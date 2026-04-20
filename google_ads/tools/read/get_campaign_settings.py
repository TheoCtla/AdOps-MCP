"""Tool: google_ads_get_campaign_settings.

Détail complet de la configuration d'UNE campagne : réseaux, ciblage
géo, enchères, budget, dates, etc. Utile pour audit ou pré-modification.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import micros_to_euros
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_money,
)
from google_ads.queries import CAMPAIGN_SETTINGS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_campaign_settings"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the full configuration of a single Google Ads campaign: channel type, bidding "
        "strategy (with target CPA/ROAS values), network settings, geo-targeting type, "
        "start/end dates, and budget details.\n"
        "\n"
        "Returns a JSON object with `customer_id` and `campaign` (object). The campaign object "
        "contains: campaign_id, name, status, channel_type (SEARCH/DISPLAY/VIDEO/...), "
        "channel_sub_type (or null), bidding_strategy, target_cpa (euros, null if N/A), "
        "target_roas (ratio, null if N/A), networks (google_search/search_network/"
        "content_network booleans), geo_targeting (positive_type/negative_type enums), "
        "start_date, end_date (null if no end), budget (daily_amount in euros, delivery_method, "
        "type). No date range — this returns settings, not metrics.\n"
        "\n"
        "Use this tool to audit a campaign's configuration before making changes, understand "
        "why a campaign behaves a certain way, check the bidding strategy and targets, or "
        "verify network and geo settings. Requires a specific campaign_id — call "
        "google_ads_get_campaign_performance first to find it."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": (
                    "Google Ads client account ID (10 digits). "
                    "Use google_ads_list_accounts first to find it."
                ),
            },
            "campaign_id": {
                "type": "string",
                "description": (
                    "Numeric campaign ID to inspect. Use "
                    "google_ads_get_campaign_performance to find it."
                ),
            },
        },
        "required": ["customer_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_campaign_settings."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload(
            "Paramètre 'campaign_id' requis. Utilise "
            "google_ads_get_campaign_performance pour le trouver."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = CAMPAIGN_SETTINGS_QUERY.format(campaign_id=campaign_id)

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        rows = list(response)
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_campaign_settings")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not rows:
        return error_payload(
            f"Aucune campagne trouvée avec campaign_id={campaign_id} "
            f"sur le compte {customer_id}."
        )

    row = rows[0]
    c = row.campaign
    b = row.campaign_budget
    ns = c.network_settings
    geo = c.geo_target_type_setting

    target_cpa_micros = c.target_cpa.target_cpa_micros
    target_cpa = round_money(micros_to_euros(target_cpa_micros)) if target_cpa_micros else None

    target_roas_val = c.target_roas.target_roas
    target_roas = round(target_roas_val, 2) if target_roas_val else None

    campaign_data = {
        "campaign_id": str(c.id),
        "name": c.name or "",
        "status": enum_name(c.status),
        "channel_type": enum_name(c.advertising_channel_type),
        "channel_sub_type": enum_name(c.advertising_channel_sub_type)
        if c.advertising_channel_sub_type
        else None,
        "bidding_strategy": enum_name(c.bidding_strategy_type),
        "target_cpa": target_cpa,
        "target_roas": target_roas,
        "networks": {
            "google_search": bool(ns.target_google_search),
            "search_network": bool(ns.target_search_network),
            "content_network": bool(ns.target_content_network),
        },
        "geo_targeting": {
            "positive_type": enum_name(geo.positive_geo_target_type),
            "negative_type": enum_name(geo.negative_geo_target_type),
        },
        "start_date": None,
        "end_date": None,
        "budget": {
            "daily_amount": round_money(micros_to_euros(b.amount_micros)),
            "delivery_method": enum_name(b.delivery_method),
            "type": enum_name(b.type_),
        },
    }

    payload = {
        "customer_id": customer_id,
        "campaign": campaign_data,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
