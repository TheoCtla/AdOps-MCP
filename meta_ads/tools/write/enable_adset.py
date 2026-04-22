"""Tool: meta_ads_enable_adset.

Réactive un ad set Meta Ads en pause.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_enable_adset"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Enable (reactivate) a paused Meta Ads ad set, immediately resuming ad delivery "
        "for all ads in that set.\n"
        "\n"
        "Returns a JSON confirmation with success status and the adset_id.\n"
        "\n"
        "Use this tool when the user wants to reactivate a previously paused ad set.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Enabling an ad set resumes ad delivery immediately "
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
            "adset_id": {
                "type": "string",
                "description": (
                    "Numeric ad set ID to enable. Use "
                    "meta_ads_get_adset_performance to find it."
                ),
            },
        },
        "required": ["ad_account_id", "adset_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_enable_adset."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adset import AdSet

        adset = AdSet(adset_id)
        adset[AdSet.Field.status] = AdSet.Status.active
        adset.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_enable_adset")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "ENABLED",
        "resource": "adset",
        "adset_id": adset_id,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
