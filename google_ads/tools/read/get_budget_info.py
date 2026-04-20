"""Tool: google_ads_get_budget_info.

Budget et pacing en temps réel de toutes les campagnes actives — budget
quotidien configuré vs dépense du jour en cours. Monitoring intra-day.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import micros_to_euros, safe_ratio
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    round_money,
    round_ratio,
)
from google_ads.queries import BUDGET_INFO_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_budget_info"


def _pacing_status(pacing_pct: float | None) -> str:
    """Détermine le statut de pacing à partir du ratio cost/budget."""
    if pacing_pct is None:
        return "NO_BUDGET"
    if pacing_pct > 1.0:
        return "OVER_BUDGET"
    if pacing_pct > 0.9:
        return "NEAR_LIMIT"
    return "ON_TRACK"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the daily budget and current-day spend (pacing) for all ENABLED campaigns on "
        "a Google Ads advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date` (today, YYYY-MM-DD), "
        "`total_campaigns`, `total_daily_budget` (sum of all daily budgets in euros), "
        "`total_cost_today` (sum of today's spend), `total_pacing_pct` (overall ratio), and "
        "`campaigns` (array sorted by pacing_pct desc — campaigns closest to their budget "
        "limit appear first). Each entry contains: campaign_id, campaign_name, daily_budget "
        "(euros), budget_type, cost_today (euros — today's partial spend), pacing_pct "
        "(cost_today / daily_budget via safe_ratio, null when daily_budget is 0), status "
        "(ON_TRACK / NEAR_LIMIT when >90% / OVER_BUDGET when >100% / NO_BUDGET). Note: "
        "today's metrics are partial by definition — they reflect spend up to the current "
        "moment, not end-of-day totals.\n"
        "\n"
        "Use this tool for intra-day budget monitoring: check which campaigns are close to "
        "exhausting their daily budget, detect over-delivery, or answer 'are we on track "
        "for today?'. No date range parameter — always queries today."
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
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_budget_info."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
    except ValueError as ex:
        return error_payload(str(ex))

    today = date.today().isoformat()

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = BUDGET_INFO_QUERY.format(today=today)

    campaigns: list[dict[str, Any]] = []
    total_budget_micros = 0
    total_cost_micros = 0

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            budget_micros = int(row.campaign_budget.amount_micros or 0)
            cost_micros = int(row.metrics.cost_micros or 0)
            daily_budget = micros_to_euros(budget_micros) or 0.0
            cost_today = micros_to_euros(cost_micros) or 0.0
            pacing_pct = safe_ratio(cost_today, daily_budget, decimals=4)

            campaigns.append(
                {
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name or "",
                    "daily_budget": round_money(daily_budget),
                    "budget_type": enum_name(row.campaign_budget.type_),
                    "cost_today": round_money(cost_today),
                    "pacing_pct": round_ratio(pacing_pct),
                    "status": _pacing_status(pacing_pct),
                }
            )

            total_budget_micros += budget_micros
            total_cost_micros += cost_micros
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_budget_info")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    campaigns.sort(key=lambda c: c["pacing_pct"] or 0, reverse=True)

    total_daily_budget = micros_to_euros(total_budget_micros) or 0.0
    total_cost_today = micros_to_euros(total_cost_micros) or 0.0

    payload = {
        "customer_id": customer_id,
        "date": today,
        "total_campaigns": len(campaigns),
        "total_daily_budget": round_money(total_daily_budget),
        "total_cost_today": round_money(total_cost_today),
        "total_pacing_pct": round_ratio(
            safe_ratio(total_cost_today, total_daily_budget, decimals=4)
        ),
        "campaigns": campaigns,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
