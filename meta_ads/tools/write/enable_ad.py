"""Tool: meta_ads_enable_ad.

Réactive une annonce Meta Ads en pause.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_enable_ad"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Enable (reactivate) a paused Meta Ads ad, immediately resuming its delivery.\n"
        "\n"
        "Returns a JSON confirmation with success status and the ad_id.\n"
        "\n"
        "Use this tool when the user wants to reactivate a previously paused ad.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Enabling an ad resumes its delivery immediately and "
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
                    "Numeric ad ID to enable. Use "
                    "meta_ads_get_ad_performance to find it."
                ),
            },
        },
        "required": ["ad_account_id", "ad_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_enable_ad."""
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
            "POST", [ad_id], params={"status": "ACTIVE"},
        ).json()

        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            return error_payload(
                f"Erreur Meta : {err.get('message', str(err))}"
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_enable_ad")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "ENABLED",
        "resource": "ad",
        "ad_id": ad_id,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
