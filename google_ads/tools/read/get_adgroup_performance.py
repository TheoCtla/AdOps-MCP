"""Tool: google_ads_get_adgroup_performance.

Détail par ad group des mêmes métriques que le tool campaign-level, pour
drill-down depuis une campagne vers ses groupes d'annonces.
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
    ALLOWED_PERF_STATUSES,
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_money,
)
from google_ads.queries import ADGROUP_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_adgroup_performance"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch per-ad-group performance metrics for a single Google Ads advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `total_ad_groups`, `totals` "
        "(aggregated impressions, clicks, cost in euros, conversions), and `ad_groups` (array "
        "sorted by cost desc). Each entry contains: ad_group_id, ad_group_name, type "
        "(SEARCH_STANDARD/DISPLAY_STANDARD/...), status, cpc_bid (euros, null if none), "
        "campaign_id, campaign_name, impressions, clicks, cost, conversions, conversion_value, "
        "ctr, avg_cpc, cpa, roas.\n"
        "\n"
        "Use this tool to drill down from campaign-level into ad-group-level detail: find the "
        "best and worst ad groups, check CPC bids, compare ad groups across a campaign. Pass "
        "`campaign_id` to scope the query to one campaign (typically after the user calls "
        "google_ads_get_campaign_performance and picks a campaign to investigate). Defaults "
        "to ENABLED ad groups over the last 7 full days (J-8 to J-1)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": (
                    "Google Ads client account ID (10 digits, dashes accepted). "
                    "Use google_ads_list_accounts first to find it."
                ),
            },
            "campaign_id": {
                "type": "string",
                "description": (
                    "Optional numeric campaign ID to scope the query to a single "
                    "campaign. If omitted, returns ad groups across all campaigns "
                    "matching the status filter."
                ),
            },
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-8.",
            },
            "date_to": {
                "type": "string",
                "description": "End of window (YYYY-MM-DD). Default: J-1 (yesterday).",
            },
            "status": {
                "type": "string",
                "enum": ["ENABLED", "PAUSED", "REMOVED"],
                "description": "Ad-group status filter. Default: ENABLED.",
                "default": "ENABLED",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_adgroup_performance."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    status = args.get("status") or "ENABLED"
    if status not in ALLOWED_PERF_STATUSES:
        return error_payload(
            f"Statut invalide : '{status}'. Valeurs acceptées : "
            + ", ".join(sorted(ALLOWED_PERF_STATUSES))
            + "."
        )

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    extra_where = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = ADGROUP_PERFORMANCE_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        status=status,
        extra_where=extra_where,
    )

    ad_groups: list[dict[str, Any]] = []
    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversions = float(row.metrics.conversions or 0.0)
            conversion_value = float(row.metrics.conversions_value or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            ad_groups.append(
                {
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name or "",
                    "type": enum_name(row.ad_group.type_),
                    "status": enum_name(row.ad_group.status),
                    "cpc_bid": round_money(
                        micros_to_euros(row.ad_group.cpc_bid_micros)
                    ),
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
                    "roas": safe_ratio(conversion_value, cost_euros, decimals=2),
                }
            )

            total_impressions += impressions
            total_clicks += clicks
            total_cost_micros += cost_micros
            total_conversions += conversions
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_adgroup_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_ad_groups": len(ad_groups),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
        },
        "ad_groups": ad_groups,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
