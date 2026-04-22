"""Tool: meta_ads_pause_campaign.

Met en pause une campagne Meta Ads.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_pause_campaign"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Pause a Meta Ads campaign, immediately stopping all ad delivery for that campaign.\n"
        "\n"
        "Returns a JSON confirmation with success status and the campaign_id.\n"
        "\n"
        "Use this tool when the user wants to stop a campaign from spending. Use "
        "meta_ads_enable_campaign to reactivate.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Pausing a campaign stops all ad delivery immediately "
        "and impacts live campaigns."
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
                "description": (
                    "Numeric campaign ID to pause. Use "
                    "meta_ads_get_campaign_performance to find it."
                ),
            },
        },
        "required": ["ad_account_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_pause_campaign."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    campaign_id = args.get("campaign_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.campaign import Campaign

        campaign = Campaign(campaign_id)
        campaign[Campaign.Field.status] = Campaign.Status.paused
        campaign.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_pause_campaign")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "PAUSED",
        "resource": "campaign",
        "campaign_id": campaign_id,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
