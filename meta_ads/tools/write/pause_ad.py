"""Tool: meta_ads_pause_ad.

Met en pause une annonce Meta Ads individuelle.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_pause_ad"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Pause a specific Meta Ads ad, immediately stopping its delivery while other ads "
        "in the same ad set continue serving.\n"
        "\n"
        "Returns a JSON confirmation with success status and the ad_id.\n"
        "\n"
        "Use this tool when the user wants to stop a specific underperforming ad without "
        "pausing the entire ad set.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Pausing an ad stops its delivery immediately and "
        "impacts live campaigns."
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
            "ad_id": {
                "type": "string",
                "description": (
                    "Numeric ad ID to pause. Use "
                    "meta_ads_get_ad_performance to find it."
                ),
            },
        },
        "required": ["ad_account_id", "ad_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_pause_ad."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    ad_id = args.get("ad_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.api import FacebookAdsApi

        api = FacebookAdsApi.get_default_api()
        resp = api.call(
            "POST", [ad_id], params={"status": "PAUSED"},
        ).json()

        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            return error_payload(
                f"Erreur Meta : {err.get('message', str(err))}"
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_pause_ad")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "PAUSED",
        "resource": "ad",
        "ad_id": ad_id,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
