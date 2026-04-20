"""Tool: google_ads_get_geo_performance.

Performance par zone géographique (pays, région, ville) — identifie les
zones qui convertissent et celles qui gaspillent du budget.
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
from google_ads.queries import GEO_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_geo_performance"

_ALLOWED_LOCATION_TYPES = frozenset({"COUNTRY", "CITY", "ALL"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch performance metrics segmented by geographic location (country, region, or city) "
        "for a Google Ads advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters`, `totals` "
        "(aggregated impressions, clicks, cost, conversions, conversion_value), and `breakdown` "
        "(array sorted by cost desc, capped at 100 rows). Each entry contains: "
        "country_criterion_id (Google Ads geo_target_constant ID — e.g. 2250=France, 2840=USA, "
        "1006094=Paris; this is an ID, not a human-readable name — Claude can interpret common "
        "IDs from its knowledge, or consult the Google Ads geo_target_constant documentation "
        "for exotic IDs), location_type (COUNTRY / REGION / CITY), campaign_id, campaign_name, "
        "impressions, clicks, cost (euros), conversions, conversion_value, ctr, avg_cpc, cpa.\n"
        "\n"
        "Use this tool to identify which geographic areas drive performance or waste budget, "
        "compare countries or cities, or investigate whether a campaign should exclude certain "
        "regions. Filter by `location_type` to focus on a specific granularity. Defaults to "
        "ALL location types over J-8 to J-1."
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
            "location_type": {
                "type": "string",
                "enum": ["COUNTRY", "CITY", "ALL"],
                "description": (
                    "Filter by location granularity. COUNTRY returns only country-level "
                    "rows, CITY only city-level. ALL returns all levels mixed. "
                    "Default: ALL."
                ),
                "default": "ALL",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_geo_performance."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    location_type = (args.get("location_type") or "ALL").upper()
    if location_type not in _ALLOWED_LOCATION_TYPES:
        return error_payload(
            f"location_type invalide : '{location_type}'. Valeurs acceptées : "
            + ", ".join(sorted(_ALLOWED_LOCATION_TYPES))
            + "."
        )

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    extra_filters: list[str] = []
    if campaign_id:
        extra_filters.append(f"AND campaign.id = {campaign_id}")
    if location_type != "ALL":
        extra_filters.append(
            f"AND geographic_view.location_type = '{location_type}'"
        )
    extra_where = "\n      ".join(extra_filters)

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = GEO_PERFORMANCE_QUERY.format(
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

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversions = float(row.metrics.conversions or 0.0)
            conversion_value = float(row.metrics.conversions_value or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            breakdown.append(
                {
                    "country_criterion_id": str(
                        row.geographic_view.country_criterion_id
                    ),
                    "location_type": enum_name(
                        row.geographic_view.location_type
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
        log.exception("Erreur inattendue dans google_ads_get_geo_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "filters": {
            "campaign_id": campaign_id or None,
            "location_type": location_type,
        },
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
            "conversion_value": round_money(total_conversion_value),
        },
        "breakdown": breakdown,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
