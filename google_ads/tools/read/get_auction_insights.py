"""Tool: google_ads_get_auction_insights.

Données concurrentielles : qui enchérit sur les mêmes mots-clés, avec
quelle visibilité et quel taux de surclassement. Requiert un campaign_id.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import default_date_range
from google_ads.helpers import (
    clean_customer_id,
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_ratio,
)
from google_ads.queries import AUCTION_INSIGHTS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_auction_insights"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch auction insights (competitive landscape) for a specific Google Ads search "
        "campaign: who else bids on the same keywords and how visible they are.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `campaign_id`, `date_range`, "
        "`total_competitors`, and `competitors` (array sorted by impression_share desc). Each "
        "entry contains: domain (competitor's display domain), impression_share, overlap_rate, "
        "position_above_rate, top_impression_pct, abs_top_impression_pct, outranking_share — "
        "all ratios between 0 and 1.\n"
        "\n"
        "Use this tool when the user asks about competitors, wants to understand who they "
        "compete against on Search, needs to diagnose lost impression share due to rank, or "
        "wants to benchmark their visibility. Requires a campaign_id — auction insights are "
        "always scoped to a specific campaign. Defaults to J-8 to J-1."
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
                    "Numeric campaign ID (REQUIRED). Auction insights must be "
                    "scoped to a campaign. Use google_ads_get_campaign_performance "
                    "to find it."
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
        "required": ["customer_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_auction_insights."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload(
            "campaign_id est requis pour les auction insights. Utilise "
            "google_ads_get_campaign_performance pour trouver l'ID de la "
            "campagne à analyser."
        )

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = AUCTION_INSIGHTS_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        campaign_id=campaign_id,
    )

    competitors: list[dict[str, Any]] = []

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            m = row.metrics
            competitors.append(
                {
                    "domain": row.segments.auction_insight_domain or "",
                    "impression_share": round_ratio(
                        m.auction_insight_search_impression_share
                    ),
                    "overlap_rate": round_ratio(
                        m.auction_insight_search_overlap_rate
                    ),
                    "position_above_rate": round_ratio(
                        m.auction_insight_search_position_above_rate
                    ),
                    "top_impression_pct": round_ratio(
                        m.auction_insight_search_top_impression_percentage
                    ),
                    "abs_top_impression_pct": round_ratio(
                        m.auction_insight_search_absolute_top_impression_percentage
                    ),
                    "outranking_share": round_ratio(
                        m.auction_insight_search_outranking_share
                    ),
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_auction_insights")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    competitors.sort(
        key=lambda c: c["impression_share"] or 0, reverse=True,
    )

    payload = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_competitors": len(competitors),
        "competitors": competitors,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
