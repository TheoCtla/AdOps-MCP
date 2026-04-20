"""Tool: google_ads_get_bid_modifiers.

Ajustements d'enchères (bid modifiers) configurés sur une campagne :
device, location, audience, ad schedule, etc.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    numeric_id,
)
from google_ads.queries import BID_MODIFIERS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_bid_modifiers"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch all bid modifiers configured on a specific Google Ads campaign: device, "
        "location, ad schedule, audience, age range, gender, and other criterion-level "
        "adjustments.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `campaign_id`, `campaign_name`, "
        "`total_modifiers`, and `modifiers` (array). Each entry contains: criterion_id, type "
        "(DEVICE / LOCATION / AD_SCHEDULE / USER_LIST / AGE_RANGE / GENDER / ...), "
        "bid_modifier (float — 1.0 = neutral, >1.0 = boost, <1.0 = reduce, 0 = exclusion), "
        "campaign_id, campaign_name. No date range — these are settings.\n"
        "\n"
        "Use this tool to audit the bid adjustment strategy of a campaign, check if device or "
        "location modifiers explain performance anomalies, or verify adjustments before "
        "recommending changes. A campaign with no modifiers uses flat bids across all "
        "dimensions."
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
    """Handler for google_ads_get_bid_modifiers."""
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
    query = BID_MODIFIERS_QUERY.format(campaign_id=campaign_id)

    modifiers: list[dict[str, Any]] = []
    campaign_name = ""

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            cc = row.campaign_criterion
            campaign_name = row.campaign.name or ""

            modifiers.append(
                {
                    "criterion_id": str(cc.criterion_id),
                    "type": enum_name(cc.type_),
                    "bid_modifier": round(cc.bid_modifier, 2) if cc.bid_modifier else None,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": campaign_name,
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_bid_modifiers")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "total_modifiers": len(modifiers),
        "modifiers": modifiers,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
