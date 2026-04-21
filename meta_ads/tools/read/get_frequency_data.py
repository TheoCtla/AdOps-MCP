"""Tool: meta_ads_get_frequency_data.

Reach et fréquence détaillés par ad set pour détecter la fatigue
créative (frequency > 3-4).
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

TOOL_NAME = "meta_ads_get_frequency_data"

_INSIGHT_FIELDS = [
    "adset_id", "adset_name", "campaign_name",
    "impressions", "reach", "frequency", "spend",
    "actions", "cost_per_action_type",
]


def _fatigue_risk(frequency: float) -> str:
    if frequency > 4:
        return "HIGH"
    if frequency > 3:
        return "MEDIUM"
    if frequency > 2:
        return "LOW"
    return "NONE"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch reach and frequency data per ad set for a Meta Ads account, with a fatigue "
        "risk indicator.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `date_range`, `total_adsets`, "
        "`high_fatigue_count`, and `adsets` (array sorted by frequency desc — most at-risk "
        "first). Each entry contains: adset_id, adset_name, campaign_name, impressions, "
        "reach, frequency, spend, leads, cpa_lead, fatigue_risk (HIGH if frequency > 4, "
        "MEDIUM > 3, LOW > 2, NONE otherwise). High frequency means the same people see "
        "the same ads too often, which typically degrades performance.\n"
        "\n"
        "Use this tool to detect creative fatigue, identify ad sets that need new creatives "
        "or broader audiences, or prioritize refresh efforts. Pass campaign_id to scope to "
        "one campaign. Defaults to J-8 to J-1."
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
    """Handler for meta_ads_get_frequency_data."""
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

        for ins in insights_cursor:
            if len(results) >= limit:
                truncated = True
                break

            freq = safe_float(ins.get("frequency"))

            results.append(
                {
                    "adset_id": ins.get("adset_id"),
                    "adset_name": ins.get("adset_name"),
                    "campaign_name": ins.get("campaign_name"),
                    "impressions": int(ins.get("impressions", 0)),
                    "reach": int(ins.get("reach", 0)),
                    "frequency": round(freq, 2),
                    "spend": round(safe_float(ins.get("spend")), 2),
                    "leads": parse_actions(ins.get("actions"), "lead"),
                    "cpa_lead": parse_cost_per_action(
                        ins.get("cost_per_action_type"), "lead",
                    ),
                    "fatigue_risk": _fatigue_risk(freq),
                }
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_frequency_data")
        return error_payload(format_meta_error(ex))

    # Sort by frequency descending — most at-risk first.
    results.sort(key=lambda r: r["frequency"], reverse=True)

    high_count = sum(1 for r in results if r["fatigue_risk"] == "HIGH")

    payload = {
        "ad_account_id": ad_account_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_adsets": len(results),
        "high_fatigue_count": high_count,
        "adsets": results,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
