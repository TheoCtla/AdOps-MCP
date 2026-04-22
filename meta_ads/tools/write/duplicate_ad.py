"""Tool: meta_ads_duplicate_ad.

Duplique une ad Meta existante, optionnellement dans un autre ad set.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_duplicate_ad"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Duplicate an existing Meta Ads ad, optionally into a different ad set. The copy is "
        "created in PAUSED status by default.\n"
        "\n"
        "Returns a JSON confirmation with the source ad_id and the new ad_id.\n"
        "\n"
        "Use this tool to quickly duplicate a high-performing ad into another ad set, or "
        "create a copy for A/B testing. Pass new_adset_id to copy into a different ad set.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new ad is created as a copy of the source ad."
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
                "description": "Numeric ad ID to duplicate.",
            },
            "new_name": {
                "type": "string",
                "description": "Optional suffix or name for the copy.",
            },
            "new_adset_id": {
                "type": "string",
                "description": "Optional ad set ID to copy the ad into.",
            },
            "status": {
                "type": "string",
                "enum": ["PAUSED", "ACTIVE"],
                "description": "Status of the copy. Default: PAUSED.",
                "default": "PAUSED",
            },
        },
        "required": ["ad_account_id", "ad_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_duplicate_ad."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    ad_id = args.get("ad_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")

    new_name = args.get("new_name")
    new_adset_id = args.get("new_adset_id")
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
        if new_adset_id:
            params["adset_id"] = new_adset_id

        resp = api.call("POST", [ad_id, "copies"], params=params).json()

        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            return error_payload(
                f"Erreur Meta : {err.get('message', str(err))}"
            )

        # The response contains the copied ad(s).
        copied = resp.get("copied_ad_id") or resp.get("ad_object_ids", [None])[0]
        new_ad_id = str(copied) if copied else None
    except Exception as ex:
        log.exception("Erreur dans meta_ads_duplicate_ad")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "DUPLICATED_AD",
        "source_ad_id": ad_id,
        "new_ad_id": new_ad_id,
        "status": status,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
