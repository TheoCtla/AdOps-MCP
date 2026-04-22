"""Tool: meta_ads_update_ad_url.

Modifie l'URL de destination d'une ad Meta.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_ad_url"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the destination URL of a Meta Ads ad.\n"
        "\n"
        "Returns a JSON confirmation with the new URL.\n"
        "\n"
        "Use this tool to change where an ad sends users — e.g. redirect to a new landing "
        "page, fix a broken URL, or update for a new promotion. The URL must start with "
        "http:// or https://.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The URL change takes effect immediately and impacts "
        "live ads."
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
                "description": "Numeric ad ID to update.",
            },
            "new_url": {
                "type": "string",
                "description": (
                    "New destination URL (must start with http:// or https://)."
                ),
            },
        },
        "required": ["ad_account_id", "ad_id", "new_url"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_ad_url."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    ad_id = args.get("ad_id")
    new_url = args.get("new_url", "")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")
    if not isinstance(new_url, str) or not new_url.startswith(("http://", "https://")):
        return error_payload("new_url doit commencer par http:// ou https://.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.ad import Ad

        ad = Ad(ad_id)
        ad_data = ad.api_get(fields=["creative"])
        creative_id = (ad_data.get("creative") or {}).get("id")

        if not creative_id:
            return error_payload(
                "Impossible de récupérer le creative actuel de cette ad."
            )

        ad.api_update(
            fields=[],
            params={
                "creative": {"creative_id": creative_id, "object_url": new_url},
            },
        )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_ad_url")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "UPDATED_URL",
        "ad_id": ad_id,
        "new_url": new_url,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
