"""Tool: google_ads_get_campaign_performance.

Retourne les métriques de performance agrégées par campagne sur une
période, pour un compte client Google Ads donné.
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
    escape_gaql_string,
    format_google_ads_error,
    round_money,
    round_ratio,
)
from google_ads.queries import CAMPAIGN_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_campaign_performance"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch per-campaign performance metrics for a single Google Ads advertiser account "
        "over a date range.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range` ({from, to}), `total_campaigns` "
        "(int), `totals` (aggregated impressions, clicks, cost in euros, conversions across all "
        "returned campaigns), and `campaigns` (array sorted by cost desc). Each campaign entry "
        "contains: campaign_id, campaign_name, type (SEARCH/DISPLAY/VIDEO/...), status, "
        "bidding_strategy, daily_budget (euros), impressions, clicks, cost (euros), conversions, "
        "conversion_value, ctr (ratio, e.g. 0.0721 = 7.21%), avg_cpc (euros), cpa "
        "(cost_per_conversion in euros), roas (conversion_value / cost, null if cost=0), and "
        "search_impression_share (ratio, null when not applicable e.g. non-search campaigns). "
        "All monetary values are in the account currency, already converted from micros.\n"
        "\n"
        "Use this tool whenever the user asks about campaign-level performance, wants a "
        "weekly/monthly campaign report, compares campaigns, identifies the biggest spenders, "
        "checks ROAS or CPA per campaign, or investigates which campaigns drive conversions. "
        "Call google_ads_list_accounts first to discover the customer_id if it is not already "
        "known. Defaults to ENABLED campaigns over the last 7 full days (J-8 to J-1) — J-1 "
        "rather than today because same-day metrics are partial and misleading."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": (
                    "Google Ads client account ID (10 digits, dashes are accepted and "
                    "stripped). This is the advertiser account to query, NOT the MCC. "
                    "Use google_ads_list_accounts first to find it."
                ),
            },
            "date_from": {
                "type": "string",
                "description": (
                    "Start of the reporting window, inclusive. Format YYYY-MM-DD. "
                    "Default: 8 days ago (J-8)."
                ),
            },
            "date_to": {
                "type": "string",
                "description": (
                    "End of the reporting window, inclusive. Format YYYY-MM-DD. "
                    "Default: yesterday (J-1). Today is avoided because same-day "
                    "metrics are partial."
                ),
            },
            "campaign_name": {
                "type": "string",
                "description": (
                    "Optional case-insensitive substring filter on campaign.name. "
                    "Example: 'Brand' matches 'Search - Brand' and 'brand-generic'."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["ENABLED", "PAUSED", "REMOVED"],
                "description": (
                    "Filter campaigns by status. Default: ENABLED. Use PAUSED or "
                    "REMOVED to audit inactive campaigns."
                ),
                "default": "ENABLED",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_campaign_performance."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
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

    extra_where = ""
    campaign_name = args.get("campaign_name")
    if isinstance(campaign_name, str) and campaign_name.strip():
        escaped = escape_gaql_string(campaign_name.strip())
        extra_where = f"AND campaign.name CONTAINS_IGNORE_CASE '{escaped}'"

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = CAMPAIGN_PERFORMANCE_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        status=status,
        extra_where=extra_where,
    )

    campaigns: list[dict[str, Any]] = []
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

            # search_impression_share : 0 = non applicable (non-search), on renvoie null.
            sis_raw = float(row.metrics.search_impression_share or 0.0)
            sis = round_ratio(sis_raw) if sis_raw > 0 else None

            campaigns.append(
                {
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name or "",
                    "type": enum_name(row.campaign.advertising_channel_type),
                    "status": enum_name(row.campaign.status),
                    "bidding_strategy": enum_name(row.campaign.bidding_strategy_type),
                    "daily_budget": round_money(
                        micros_to_euros(row.campaign_budget.amount_micros)
                    ),
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": round_money(cost_euros),
                    "conversions": round(conversions, 2),
                    "conversion_value": round_money(conversion_value),
                    "ctr": safe_ratio(clicks, impressions, decimals=4),
                    "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                    "cpa": safe_ratio(cost_euros, conversions, decimals=2),
                    "roas": safe_ratio(conversion_value, cost_euros, decimals=2),
                    "search_impression_share": sis,
                }
            )

            total_impressions += impressions
            total_clicks += clicks
            total_cost_micros += cost_micros
            total_conversions += conversions
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_campaign_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_campaigns": len(campaigns),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
        },
        "campaigns": campaigns,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
