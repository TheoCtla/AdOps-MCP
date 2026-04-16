"""Tool: google_ads_get_daily_performance.

Série temporelle jour par jour des métriques de performance. Optionnelle-
ment scopée à une campagne ; sinon renvoie aussi un breakdown (date,
campagne) utile pour détecter des anomalies spécifiques.
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
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_money,
)
from google_ads.queries import DAILY_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_daily_performance"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch day-by-day performance metrics for a Google Ads account, optionally scoped to "
        "a single campaign.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `days` (one entry per day, "
        "sorted ascending) and, when no campaign_id is provided, `campaigns_breakdown` (one "
        "entry per (date, campaign) pair). Each day entry contains: date (YYYY-MM-DD), "
        "impressions, clicks, cost (euros), conversions, conversion_value, avg_cpc (euros, "
        "clicks-weighted: cost/clicks, null if 0 clicks), ctr (clicks/impressions, null if 0 "
        "impressions). Breakdown entries additionally include campaign_id and campaign_name.\n"
        "\n"
        "Use this tool when the user asks for a time series, wants to spot day-of-week trends, "
        "check performance over the last month, find a spend anomaly on a specific day, or "
        "build a graph. Defaults to the last 30 full days (J-30 to J-1). Only ENABLED "
        "campaigns are included. Pass `campaign_id` to restrict the series to one campaign."
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
                    "contains only `days` (no campaigns_breakdown)."
                ),
            },
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-30.",
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
    """Handler for google_ads_get_daily_performance."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    default_from, default_to = default_date_range(days_back=29)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    extra_where = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = DAILY_PERFORMANCE_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        extra_where=extra_where,
    )

    # Agrégats sommés en micros pour éviter les pertes d'arrondi.
    day_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "impressions": 0,
            "clicks": 0,
            "cost_micros": 0,
            "conversions": 0.0,
            "conversion_value": 0.0,
        }
    )
    breakdown_rows: list[dict[str, Any]] = []

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            day = row.segments.date
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            cost_micros = int(row.metrics.cost_micros or 0)
            conversions = float(row.metrics.conversions or 0.0)
            conversion_value = float(row.metrics.conversions_value or 0.0)

            agg = day_totals[day]
            agg["impressions"] += impressions
            agg["clicks"] += clicks
            agg["cost_micros"] += cost_micros
            agg["conversions"] += conversions
            agg["conversion_value"] += conversion_value

            if not campaign_id:
                cost_euros = micros_to_euros(cost_micros) or 0.0
                breakdown_rows.append(
                    {
                        "date": day,
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name or "",
                        "impressions": impressions,
                        "clicks": clicks,
                        "cost": round_money(cost_euros),
                        "conversions": round(conversions, 2),
                        "conversion_value": round_money(conversion_value),
                        "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                        "ctr": safe_ratio(clicks, impressions, decimals=4),
                    }
                )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_daily_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    days: list[dict[str, Any]] = []
    for day in sorted(day_totals):
        agg = day_totals[day]
        impressions = int(agg["impressions"])
        clicks = int(agg["clicks"])
        cost_euros = micros_to_euros(int(agg["cost_micros"])) or 0.0

        days.append(
            {
                "date": day,
                "impressions": impressions,
                "clicks": clicks,
                "cost": round_money(cost_euros),
                "conversions": round(agg["conversions"], 2),
                "conversion_value": round_money(agg["conversion_value"]),
                "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                "ctr": safe_ratio(clicks, impressions, decimals=4),
            }
        )

    payload: dict[str, Any] = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "days": days,
    }
    if not campaign_id:
        payload["campaigns_breakdown"] = breakdown_rows

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
