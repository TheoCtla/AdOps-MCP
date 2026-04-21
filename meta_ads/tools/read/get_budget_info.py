"""Tool: meta_ads_get_budget_info.

Budget et pacing en temps réel des campagnes actives d'un compte Meta.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import (
    cents_to_euros,
    error_payload,
    format_meta_error,
    safe_float,
)


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_budget_info"


def _pacing_status(pacing_pct: float | None, has_daily: bool) -> str:
    if not has_daily:
        return "NO_DAILY_BUDGET"
    if pacing_pct is None:
        return "NO_DAILY_BUDGET"
    if pacing_pct > 1.0:
        return "OVER_BUDGET"
    if pacing_pct > 0.9:
        return "NEAR_LIMIT"
    return "ON_TRACK"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the daily budget and current-day spend (pacing) for all ACTIVE campaigns on "
        "a Meta Ads account.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `date`, `total_campaigns`, "
        "`total_daily_budget`, `total_cost_today`, `total_pacing_pct`, and `campaigns` "
        "(array sorted by pacing_pct desc). Each entry contains: campaign_id, campaign_name, "
        "daily_budget (euros), lifetime_budget (euros), budget_remaining (euros), cost_today "
        "(euros), pacing_pct (cost_today / daily_budget), status (ON_TRACK / NEAR_LIMIT / "
        "OVER_BUDGET / NO_DAILY_BUDGET). Today's metrics are partial by definition.\n"
        "\n"
        "Use this tool for intra-day budget monitoring, detect campaigns close to exhausting "
        "their budget, or answer 'are we on track for today?'. No date range — always "
        "queries today."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "ad_account_id": {
                "type": "string",
                "description": (
                    "Meta ad account ID (format 'act_XXXXX'). "
                    "Use meta_ads_list_ad_accounts to find it."
                ),
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_budget_info."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    today = date.today().isoformat()

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        # Active campaigns with budgets.
        campaigns_cursor = account.get_campaigns(
            fields=["id", "name", "status", "daily_budget",
                    "lifetime_budget", "budget_remaining"],
            params={
                "filtering": [
                    {"field": "effective_status", "operator": "IN",
                     "value": ["ACTIVE"]}
                ],
                "limit": 100,
            },
        )

        campaigns_map: dict[str, dict[str, Any]] = {}
        for camp in campaigns_cursor:
            if len(campaigns_map) >= 100:
                break
            campaigns_map[camp["id"]] = {
                "campaign_id": camp["id"],
                "campaign_name": camp.get("name", ""),
                "daily_budget": cents_to_euros(camp.get("daily_budget")),
                "lifetime_budget": cents_to_euros(camp.get("lifetime_budget")),
                "budget_remaining": cents_to_euros(camp.get("budget_remaining")),
            }

        # Today's spend per campaign.
        insights_cursor = account.get_insights(
            fields=["campaign_id", "spend"],
            params={
                "time_range": {"since": today, "until": today},
                "level": "campaign",
                "limit": 100,
            },
        )

        spend_map: dict[str, float] = {}
        for ins in insights_cursor:
            if len(spend_map) >= 100:
                break
            spend_map[ins.get("campaign_id", "")] = safe_float(ins.get("spend"))

    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_budget_info")
        return error_payload(format_meta_error(ex))

    # Merge and compute pacing.
    results: list[dict[str, Any]] = []
    total_budget = 0.0
    total_cost = 0.0

    for cid, camp in campaigns_map.items():
        daily = camp["daily_budget"]
        cost_today = spend_map.get(cid, 0.0)
        has_daily = daily is not None and daily > 0

        if has_daily:
            pacing_pct = round(cost_today / daily, 4)
        else:
            pacing_pct = None

        camp["cost_today"] = round(cost_today, 2)
        camp["pacing_pct"] = pacing_pct
        camp["status"] = _pacing_status(pacing_pct, has_daily)
        results.append(camp)

        if has_daily:
            total_budget += daily
        total_cost += cost_today

    results.sort(key=lambda r: r["pacing_pct"] or 0, reverse=True)

    total_pacing = round(total_cost / total_budget, 4) if total_budget > 0 else None

    payload = {
        "ad_account_id": ad_account_id,
        "date": today,
        "total_campaigns": len(results),
        "total_daily_budget": round(total_budget, 2),
        "total_cost_today": round(total_cost, 2),
        "total_pacing_pct": total_pacing,
        "campaigns": results,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
