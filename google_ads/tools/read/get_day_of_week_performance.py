"""Tool: google_ads_get_day_of_week_performance.

Performance par jour de la semaine (lundi → dimanche). Même structure
que le tool hour_of_day : breakdown (jour, campagne) + agrégat
optionnel par jour toutes campagnes confondues.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
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
from google_ads.queries import DAY_OF_WEEK_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_day_of_week_performance"

_DAY_ORDER = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch performance metrics segmented by day of week (Monday through Sunday) for a "
        "Google Ads advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters`, `totals`, "
        "`breakdown` (one entry per (day_of_week, campaign) pair), and — when no campaign_id "
        "is provided — `aggregated_by_day_of_week` (7 entries, Monday to Sunday, summed "
        "across all campaigns). Each entry contains: day_of_week (MONDAY/TUESDAY/.../SUNDAY), "
        "campaign_id, campaign_name (breakdown only), impressions, clicks, cost (euros), "
        "conversions, conversion_value, ctr, avg_cpc, cpa. Days with no data still appear in "
        "the aggregation with zeroed counters and null ratios.\n"
        "\n"
        "Use this tool to find the best and worst days for conversions, identify weekend vs "
        "weekday patterns, or inform ad scheduling strategies. Only ENABLED campaigns are "
        "included. Defaults to J-8 to J-1."
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
                    "Optional numeric campaign ID. If provided, the response "
                    "contains only `breakdown` (no aggregated_by_day_of_week)."
                ),
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
    """Handler for google_ads_get_day_of_week_performance."""
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
    query = DAY_OF_WEEK_PERFORMANCE_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        extra_where=extra_where,
    )

    breakdown: list[dict[str, Any]] = []
    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0
    total_conversion_value = 0.0

    day_agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "impressions": 0,
            "clicks": 0,
            "cost_micros": 0,
            "conversions": 0.0,
            "conversion_value": 0.0,
        }
    )

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            day_name = enum_name(row.segments.day_of_week)
            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversions = float(row.metrics.conversions or 0.0)
            conversion_value = float(row.metrics.conversions_value or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            breakdown.append(
                {
                    "day_of_week": day_name,
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

            if not campaign_id:
                agg = day_agg[day_name]
                agg["impressions"] += impressions
                agg["clicks"] += clicks
                agg["cost_micros"] += cost_micros
                agg["conversions"] += conversions
                agg["conversion_value"] += conversion_value

            total_impressions += impressions
            total_clicks += clicks
            total_cost_micros += cost_micros
            total_conversions += conversions
            total_conversion_value += conversion_value
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_day_of_week_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload: dict[str, Any] = {
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
        "breakdown": breakdown,
    }

    if not campaign_id:
        aggregated: list[dict[str, Any]] = []
        for day_name in _DAY_ORDER:
            agg = day_agg[day_name]
            impressions = int(agg["impressions"])
            clicks = int(agg["clicks"])
            cost_euros = micros_to_euros(int(agg["cost_micros"])) or 0.0
            conv = agg["conversions"]
            conv_val = agg["conversion_value"]
            aggregated.append(
                {
                    "day_of_week": day_name,
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": round_money(cost_euros),
                    "conversions": round(conv, 2),
                    "conversion_value": round_money(conv_val),
                    "ctr": safe_ratio(clicks, impressions, decimals=4),
                    "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                    "cpa": safe_ratio(cost_euros, conv, decimals=2),
                }
            )
        payload["aggregated_by_day_of_week"] = aggregated

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
