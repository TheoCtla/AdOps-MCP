"""Tool: meta_ads_update_ad_name.

Renomme une ad Meta existante.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_ad_name"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Rename an existing Meta Ads ad.\n"
        "\n"
        "Returns a JSON confirmation with the new name.\n"
        "\n"
        "Use this tool to rename an ad for better organization — e.g. add a version suffix, "
        "clarify the creative variant, or align with naming conventions.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The name change takes effect immediately."
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
                "description": "Numeric ad ID to rename.",
            },
            "new_name": {
                "type": "string",
                "description": "New name for the ad.",
            },
        },
        "required": ["ad_account_id", "ad_id", "new_name"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_ad_name."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    ad_id = args.get("ad_id")
    new_name = args.get("new_name")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")
    if not new_name or not isinstance(new_name, str):
        return error_payload("Paramètre 'new_name' requis (texte non vide).")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.ad import Ad

        ad = Ad(ad_id)
        ad.api_update(fields=[], params={"name": new_name})
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_ad_name")
        from facebook_business.exceptions import FacebookRequestError

        if isinstance(ex, FacebookRequestError):
            error_detail = {
                "error": True,
                "api_error_code": ex.api_error_code(),
                "api_error_message": ex.api_error_message(),
                "api_error_type": ex.api_error_type(),
                "body": str(ex.body()),
                "http_status": ex.http_status(),
            }
            return [TextContent(type="text", text=json.dumps(error_detail, ensure_ascii=False))]
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "UPDATED_NAME",
        "ad_id": ad_id,
        "new_name": new_name,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
