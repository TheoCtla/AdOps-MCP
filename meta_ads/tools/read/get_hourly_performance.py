"""Tool: meta_ads_get_hourly_performance.

Performances par heure de la journée via le breakdown
hourly_stats_aggregated_by_advertiser_time_zone.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import (
    default_date_range,
    error_payload,
    format_meta_error,
    parse_actions,
    parse_cost_per_action,
    safe_float,
)


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_hourly_performance"

_HOURLY_BREAKDOWN = "hourly_stats_aggregated_by_advertiser_time_zone"

_INSIGHT_FIELDS = [
    "impressions", "clicks", "spend", "cpm", "cpc", "ctr",
    "actions", "cost_per_action_type",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch performance metrics broken down by hour of day for a Meta Ads account, "
        "aggregated in the advertiser's timezone.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `date_range`, `total_hours`, and "
        "`hours` (array). Each entry contains: hour (time range string, e.g. "
        "'00:00:00 - 00:59:59'), impressions, clicks, spend, cpm, cpc, ctr, leads, "
        "purchases, cpa_lead, cpa_purchase.\n"
        "\n"
        "Use this tool to find the best and worst hours for conversions, identify off-hours "
        "waste, or determine optimal ad scheduling. Pass campaign_id to scope to one "
        "campaign. Defaults to J-8 to J-1."
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
            "campaign_id": {
                "type": "string",
                "description": "Optional campaign ID to scope the query.",
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
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_hourly_performance."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    d_from, d_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or d_from
    date_to = args.get("date_to") or d_to
    campaign_id = args.get("campaign_id")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            "time_range": {"since": date_from, "until": date_to},
            "breakdowns": [_HOURLY_BREAKDOWN],
            "limit": 100,
        }
        if campaign_id:
            params["filtering"] = [
                {"field": "campaign.id", "operator": "EQUAL", "value": campaign_id}
            ]

        insights_cursor = account.get_insights(
            fields=_INSIGHT_FIELDS, params=params,
        )

        hours: list[dict[str, Any]] = []

        for ins in insights_cursor:
            if len(hours) >= 100:
                break

            hours.append(
                {
                    "hour": ins.get(_HOURLY_BREAKDOWN, ""),
                    "impressions": int(ins.get("impressions", 0)),
                    "clicks": int(ins.get("clicks", 0)),
                    "spend": round(safe_float(ins.get("spend")), 2),
                    "cpm": round(safe_float(ins.get("cpm")), 2),
                    "cpc": round(safe_float(ins.get("cpc")), 2),
                    "ctr": round(safe_float(ins.get("ctr")), 4),
                    "leads": parse_actions(ins.get("actions"), "lead"),
                    "purchases": parse_actions(ins.get("actions"), "purchase"),
                    "cpa_lead": parse_cost_per_action(
                        ins.get("cost_per_action_type"), "lead",
                    ),
                    "cpa_purchase": parse_cost_per_action(
                        ins.get("cost_per_action_type"), "purchase",
                    ),
                }
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_hourly_performance")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_hours": len(hours),
        "hours": hours,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
