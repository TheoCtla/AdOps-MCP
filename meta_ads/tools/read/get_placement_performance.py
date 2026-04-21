"""Tool: meta_ads_get_placement_performance.

Performance par placement (Facebook Feed, Instagram Stories, Reels, etc.).
Raccourci de get_audience_breakdown avec breakdown publisher_platform +
platform_position.
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

TOOL_NAME = "meta_ads_get_placement_performance"

_INSIGHT_FIELDS = [
    "impressions", "clicks", "spend", "cpm", "cpc", "ctr",
    "reach", "actions", "cost_per_action_type",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch performance metrics broken down by placement (publisher platform + position) "
        "for a Meta Ads account: Facebook Feed, Instagram Stories, Instagram Reels, Audience "
        "Network, Messenger, etc.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `date_range`, `total_placements`, and "
        "`placements` (array). Each entry contains: publisher_platform (facebook / instagram "
        "/ audience_network / messenger), platform_position (feed / story / reels / "
        "right_hand_column / ...), impressions, clicks, spend, cpm, cpc, ctr, reach, leads, "
        "purchases, cpa_lead, cpa_purchase.\n"
        "\n"
        "Use this tool to answer 'are Stories better than Feed?', compare placement costs, "
        "or identify placements that waste budget. Pass campaign_id to scope to one campaign. "
        "Defaults to J-8 to J-1."
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
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Max placements returned. Default: 50.",
                "default": 50,
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_placement_performance."""
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
    limit = min(int(args.get("limit", 50)), 200)

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            "time_range": {"since": date_from, "until": date_to},
            "breakdowns": ["publisher_platform", "platform_position"],
            "limit": limit,
        }
        if campaign_id:
            params["filtering"] = [
                {"field": "campaign.id", "operator": "EQUAL", "value": campaign_id}
            ]

        insights_cursor = account.get_insights(
            fields=_INSIGHT_FIELDS, params=params,
        )

        placements: list[dict[str, Any]] = []
        truncated = False

        for ins in insights_cursor:
            if len(placements) >= limit:
                truncated = True
                break

            placements.append(
                {
                    "publisher_platform": ins.get("publisher_platform", ""),
                    "platform_position": ins.get("platform_position", ""),
                    "impressions": int(ins.get("impressions", 0)),
                    "clicks": int(ins.get("clicks", 0)),
                    "spend": round(safe_float(ins.get("spend")), 2),
                    "cpm": round(safe_float(ins.get("cpm")), 2),
                    "cpc": round(safe_float(ins.get("cpc")), 2),
                    "ctr": round(safe_float(ins.get("ctr")), 4),
                    "reach": int(ins.get("reach", 0)),
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
        log.exception("Erreur dans meta_ads_get_placement_performance")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_placements": len(placements),
        "placements": placements,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
