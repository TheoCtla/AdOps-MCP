"""Tool: meta_ads_get_adset_performance.

Performances des ad sets Meta Ads. Un seul appel insights avec
level=adset pour éviter les timeouts et rate limits.
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

TOOL_NAME = "meta_ads_get_adset_performance"

_INSIGHT_FIELDS = [
    "adset_id", "adset_name",
    "campaign_id", "campaign_name",
    "impressions", "clicks", "spend", "cpm", "cpc", "ctr",
    "reach", "frequency", "actions", "cost_per_action_type",
    "purchase_roas",
]


def _parse_roas(ins: dict[str, Any]) -> float | None:
    roas_list = ins.get("purchase_roas")
    if roas_list and isinstance(roas_list, list) and len(roas_list) > 0:
        val = roas_list[0].get("value")
        if val is not None:
            return round(safe_float(val), 2)
    return None


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch per-ad-set performance metrics for a Meta Ads account.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `date_range`, `total_adsets`, `totals`, "
        "and `adsets` (array). Each entry contains: adset_id, adset_name, campaign_id, "
        "campaign_name, impressions, clicks, spend, cpm, cpc, ctr, reach, frequency, leads, "
        "purchases, cpa_lead, cpa_purchase, roas.\n"
        "\n"
        "Use this tool to drill down from campaign to ad-set level, compare audience segments, "
        "or find the best-performing ad sets. Pass campaign_id to scope to one campaign. "
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
                "description": "Max ad sets returned. Default: 25.",
                "default": 25,
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_adset_performance."""
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
    limit = min(int(args.get("limit", 25)), 200)

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            "time_range": {"since": date_from, "until": date_to},
            "level": "adset",
            "limit": limit,
        }
        if campaign_id:
            params["filtering"] = [
                {"field": "campaign.id", "operator": "EQUAL", "value": campaign_id}
            ]

        insights_cursor = account.get_insights(
            fields=_INSIGHT_FIELDS, params=params,
        )

        results: list[dict[str, Any]] = []
        truncated = False
        total_impressions = 0
        total_clicks = 0
        total_spend = 0.0
        total_leads = 0.0
        total_purchases = 0.0

        for ins in insights_cursor:
            if len(results) >= limit:
                truncated = True
                break

            impressions = int(ins.get("impressions", 0))
            clicks = int(ins.get("clicks", 0))
            spend = safe_float(ins.get("spend"))
            leads = parse_actions(ins.get("actions"), "lead")
            purchases = parse_actions(ins.get("actions"), "purchase")

            results.append(
                {
                    "adset_id": ins.get("adset_id"),
                    "adset_name": ins.get("adset_name"),
                    "campaign_id": ins.get("campaign_id"),
                    "campaign_name": ins.get("campaign_name"),
                    "impressions": impressions,
                    "clicks": clicks,
                    "spend": round(spend, 2),
                    "cpm": round(safe_float(ins.get("cpm")), 2),
                    "cpc": round(safe_float(ins.get("cpc")), 2),
                    "ctr": round(safe_float(ins.get("ctr")), 4),
                    "reach": int(ins.get("reach", 0)),
                    "frequency": round(safe_float(ins.get("frequency")), 2),
                    "leads": leads,
                    "purchases": purchases,
                    "cpa_lead": parse_cost_per_action(
                        ins.get("cost_per_action_type"), "lead",
                    ),
                    "cpa_purchase": parse_cost_per_action(
                        ins.get("cost_per_action_type"), "purchase",
                    ),
                    "roas": _parse_roas(ins),
                }
            )

            total_impressions += impressions
            total_clicks += clicks
            total_spend += spend
            total_leads += leads
            total_purchases += purchases
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_adset_performance")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_adsets": len(results),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "spend": round(total_spend, 2),
            "leads": total_leads,
            "purchases": total_purchases,
        },
        "adsets": results,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
