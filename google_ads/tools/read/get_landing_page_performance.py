"""Tool: google_ads_get_landing_page_performance.

Performance par page de destination — identifie les landing pages qui
convertissent mal ou qui sont lentes (speed_score).
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
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_money,
)
from google_ads.queries import LANDING_PAGE_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_landing_page_performance"

_LIMIT_DEFAULT = 50
_LIMIT_MAX = 200


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch performance metrics grouped by landing page URL for a Google Ads advertiser "
        "account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters`, `totals`, and "
        "`landing_pages` (array sorted by clicks desc, capped by `limit`). Each entry "
        "contains: url (unexpanded final URL), impressions, clicks, cost (euros), conversions, "
        "conversion_value, ctr, avg_cpc, cpa, speed_score (1-100, null when not available — "
        "Google computes this from CrUX data and it may be absent for low-traffic pages).\n"
        "\n"
        "Use this tool to find landing pages that convert poorly (high cost, low conversions), "
        "identify slow pages (low speed_score) that hurt Quality Score, or compare conversion "
        "rates across different landing pages. Defaults to J-8 to J-1, up to 50 pages."
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
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": _LIMIT_MAX,
                "description": (
                    f"Max landing pages returned. Default: {_LIMIT_DEFAULT}. "
                    f"Max: {_LIMIT_MAX}."
                ),
                "default": _LIMIT_DEFAULT,
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_landing_page_performance."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    limit_raw = args.get("limit", _LIMIT_DEFAULT)
    try:
        limit = int(limit_raw) if limit_raw is not None else _LIMIT_DEFAULT
    except (TypeError, ValueError):
        return error_payload(f"limit doit être un entier entre 1 et {_LIMIT_MAX}.")
    if limit < 1 or limit > _LIMIT_MAX:
        return error_payload(f"limit doit être entre 1 et {_LIMIT_MAX}.")

    extra_where = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = LANDING_PAGE_PERFORMANCE_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        extra_where=extra_where,
        limit=limit,
    )

    landing_pages: list[dict[str, Any]] = []
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

            speed_raw = int(row.metrics.speed_score or 0)
            speed_score = speed_raw if speed_raw > 0 else None

            landing_pages.append(
                {
                    "url": row.landing_page_view.unexpanded_final_url or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": round_money(cost_euros),
                    "conversions": round(conversions, 2),
                    "conversion_value": round_money(conversion_value),
                    "ctr": safe_ratio(clicks, impressions, decimals=4),
                    "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                    "cpa": safe_ratio(cost_euros, conversions, decimals=2),
                    "speed_score": speed_score,
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
        log.exception("Erreur inattendue dans google_ads_get_landing_page_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "filters": {
            "campaign_id": campaign_id or None,
            "limit": limit,
        },
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
            "conversion_value": round_money(total_conversion_value),
        },
        "landing_pages": landing_pages,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
