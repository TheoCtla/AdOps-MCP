"""Tool: meta_ads_duplicate_adset.

Duplique un ad set Meta entier (avec toutes ses ads), optionnellement
dans une autre campagne.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_duplicate_adset"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Duplicate an existing Meta Ads ad set (including all its ads), optionally into a "
        "different campaign. The copy is created in PAUSED status by default.\n"
        "\n"
        "Returns a JSON confirmation with the source adset_id and the new adset_id.\n"
        "\n"
        "Use this tool to quickly replicate an ad set structure — e.g. to test different "
        "audiences with the same ads, or copy a proven ad set into a new campaign. Pass "
        "new_campaign_id to copy into a different campaign.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new ad set (with all its ads) is created as a copy."
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
                "description": "Numeric ad set ID to duplicate.",
            },
            "new_name": {
                "type": "string",
                "description": "Optional suffix or name for the copy.",
            },
            "new_campaign_id": {
                "type": "string",
                "description": "Optional campaign ID to copy the ad set into.",
            },
            "status": {
                "type": "string",
                "enum": ["PAUSED", "ACTIVE"],
                "description": "Status of the copy. Default: PAUSED.",
                "default": "PAUSED",
            },
        },
        "required": ["ad_account_id", "adset_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_duplicate_adset."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")

    new_name = args.get("new_name")
    new_campaign_id = args.get("new_campaign_id")
    status = args.get("status") or "PAUSED"

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.api import FacebookAdsApi

        api = FacebookAdsApi.get_default_api()

        params: dict[str, Any] = {"status_option": status}
        if new_name:
            params["rename_options"] = {"rename_suffix": f" - {new_name}"}
        if new_campaign_id:
            params["campaign_id"] = new_campaign_id

        resp = api.call("POST", [adset_id, "copies"], params=params).json()

        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            return error_payload(
                f"Erreur Meta : {err.get('message', str(err))}"
            )

        copied = resp.get("copied_adset_id") or resp.get("ad_object_ids", [None])[0]
        new_adset_id = str(copied) if copied else None
    except Exception as ex:
        log.exception("Erreur dans meta_ads_duplicate_adset")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "DUPLICATED_ADSET",
        "source_adset_id": adset_id,
        "new_adset_id": new_adset_id,
        "status": status,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
