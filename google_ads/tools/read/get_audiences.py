"""Tool: google_ads_get_audiences.

Segments d'audience attachés aux campagnes et leurs performances.
Évalue quels segments convertissent et lesquels gaspillent du budget.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import default_date_range, micros_to_euros, safe_ratio
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_money,
)
from google_ads.queries import AUDIENCES_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_audiences"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch audience segments attached to campaigns and their performance metrics for a "
        "Google Ads advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters`, `totals`, and "
        "`audiences` (array sorted by cost desc). Each entry contains: user_list (resource "
        "name of the audience segment), type (USER_LIST / COMBINED_AUDIENCE / CUSTOM_AUDIENCE "
        "/ ...), bid_modifier (null if not set), campaign_id, campaign_name, impressions, "
        "clicks, cost (euros), conversions, conversion_value, ctr, avg_cpc, cpa.\n"
        "\n"
        "Use this tool to evaluate which audience segments drive conversions vs waste budget, "
        "audit bid adjustments on audiences, or check if any audiences are attached at all. "
        "Many Search campaigns have no audiences attached (total_audiences=0) — that is normal "
        "and simply means the campaign targets all users without audience layering. Defaults "
        "to J-8 to J-1."
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
                "description": "Optional numeric campaign ID to scope the query.",
            },
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-8.",
            },
            "date_to": {
                "type": "string",
                "description": "End of window (YYYY-MM-DD). Default: J-1.",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_audiences."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    extra_where = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = AUDIENCES_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        extra_where=extra_where,
    )

    audiences: list[dict[str, Any]] = []
    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0
    total_conversion_value = 0.0

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversions = float(row.metrics.conversions or 0.0)
            conversion_value = float(row.metrics.conversions_value or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            cc = row.campaign_criterion
            bid_mod = cc.bid_modifier
            bid_modifier = round(bid_mod, 2) if bid_mod else None

            audiences.append(
                {
                    "user_list": cc.user_list.user_list or "",
                    "type": enum_name(cc.type_),
                    "bid_modifier": bid_modifier,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": round_money(cost_euros),
                    "conversions": round(conversions, 2),
                    "conversion_value": round_money(conversion_value),
                    "ctr": safe_ratio(clicks, impressions, decimals=4),
                    "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                    "cpa": safe_ratio(cost_euros, conversions, decimals=2),
                }
            )

            total_impressions += impressions
            total_clicks += clicks
            total_cost_micros += cost_micros
            total_conversions += conversions
            total_conversion_value += conversion_value
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_audiences")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "filters": {"campaign_id": campaign_id or None},
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
            "conversion_value": round_money(total_conversion_value),
        },
        "audiences": audiences,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
