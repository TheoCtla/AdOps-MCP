"""Tool: meta_ads_update_ad_creative.

Modifie le copy d'une ad Meta existante (primary text, headline,
description, CTA) via la mise à jour du creative lié.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_ad_creative"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the creative copy of an existing Meta Ads ad: primary text (body), headline "
        "(title), link description, and/or call-to-action type.\n"
        "\n"
        "Returns a JSON confirmation with the list of updated fields.\n"
        "\n"
        "Use this tool to modify ad copy without recreating the ad — e.g. fix a typo, "
        "change the CTA, or update the headline. At least one field must be provided. "
        "Common CTA values: LEARN_MORE, SHOP_NOW, SIGN_UP, CONTACT_US, BOOK_TRAVEL, "
        "GET_OFFER, GET_QUOTE, SUBSCRIBE, APPLY_NOW.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The creative change takes effect immediately and "
        "impacts live ads."
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
            "body": {
                "type": "string",
                "description": "New primary text (body). Optional.",
            },
            "title": {
                "type": "string",
                "description": "New headline (title). Optional.",
            },
            "link_description": {
                "type": "string",
                "description": "New link description. Optional.",
            },
            "call_to_action_type": {
                "type": "string",
                "description": (
                    "New CTA type (e.g. LEARN_MORE, SHOP_NOW, SIGN_UP). Optional."
                ),
            },
        },
        "required": ["ad_account_id", "ad_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_ad_creative."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    ad_id = args.get("ad_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")

    creative_params: dict[str, str] = {}
    updated_fields: list[str] = []
    for key in ("body", "title", "link_description", "call_to_action_type"):
        val = args.get(key)
        if val is not None:
            creative_params[key] = str(val)
            updated_fields.append(key)

    if not creative_params:
        return error_payload(
            "Au moins un champ à modifier requis (body, title, "
            "link_description, call_to_action_type)."
        )

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
                "creative": {"creative_id": creative_id, **creative_params},
            },
        )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_ad_creative")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "UPDATED_CREATIVE",
        "ad_id": ad_id,
        "updated_fields": updated_fields,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
