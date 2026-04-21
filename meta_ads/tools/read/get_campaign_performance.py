"""Tool: meta_ads_get_campaign_performance.

Performances des campagnes Meta Ads (Facebook/Instagram) d'un compte pub.
Un seul appel insights avec level=campaign pour éviter les timeouts.
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

TOOL_NAME = "meta_ads_get_campaign_performance"

_INSIGHT_FIELDS = [
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
        "Fetch per-campaign performance metrics for a Meta Ads (Facebook/Instagram) ad "
        "account over a date range.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `date_range`, `total_campaigns`, "
        "`totals` (aggregated impressions, clicks, spend, leads, purchases), and `campaigns` "
        "(array). Each entry contains: campaign_id, campaign_name, impressions, clicks, "
        "spend, cpm, cpc, ctr, reach, frequency, leads, purchases, cpa_lead, cpa_purchase, "
        "roas. All monetary values in account currency.\n"
        "\n"
        "Use this tool for campaign-level reporting, comparing campaigns, identifying top "
        "spenders, or checking ROAS/CPA. Call meta_ads_list_ad_accounts first to find the "
        "ad_account_id. Defaults to the last 7 full days (J-8 to J-1)."
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
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-8.",
            },
            "date_to": {
                "type": "string",
                "description": "End of window (YYYY-MM-DD). Default: J-1.",
            },
            "campaign_name": {
                "type": "string",
                "description": (
                    "Optional case-insensitive substring filter on campaign name."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["ACTIVE", "PAUSED", "ALL"],
                "description": "Filter by campaign status. Default: ALL.",
                "default": "ALL",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Max campaigns returned. Default: 50.",
                "default": 50,
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_campaign_performance."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX'). "
            "Utilise meta_ads_list_ad_accounts pour le trouver."
        )

    d_from, d_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or d_from
    date_to = args.get("date_to") or d_to
    campaign_name = args.get("campaign_name")
    status = args.get("status") or "ALL"
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
            "level": "campaign",
            "limit": limit,
        }
        filtering: list[dict[str, Any]] = []
        if status != "ALL":
            filtering.append(
                {"field": "campaign.effective_status", "operator": "IN", "value": [status]}
            )
        if filtering:
            params["filtering"] = filtering

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

            name = ins.get("campaign_name", "")
            if campaign_name and campaign_name.lower() not in name.lower():
                continue

            impressions = int(ins.get("impressions", 0))
            clicks = int(ins.get("clicks", 0))
            spend = safe_float(ins.get("spend"))
            leads = parse_actions(ins.get("actions"), "lead")
            purchases = parse_actions(ins.get("actions"), "purchase")

            results.append(
                {
                    "campaign_id": ins.get("campaign_id"),
                    "campaign_name": name,
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
        log.exception("Erreur dans meta_ads_get_campaign_performance")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_campaigns": len(results),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "spend": round(total_spend, 2),
            "leads": total_leads,
            "purchases": total_purchases,
        },
        "campaigns": results,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
