"""Tool: meta_ads_debug_pages.

Tool temporaire de debug pour inspecter les creatives existants d'un
compte publicitaire Meta Ads.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_debug_pages"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Debug tool: inspect the structure of existing creatives on a Meta Ads account. "
        "Returns detailed creative fields (body, title, object_story_spec, page_id, "
        "instagram_actor_id, etc.) for the 2 most recent ads. Temporary — used to "
        "identify the correct IDs for ad creation."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "ad_account_id": {
                "type": "string",
                "description": "Meta ad account ID (format 'act_XXXXX').",
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_debug_pages."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    from facebook_business.adobjects.adaccount import AdAccount

    account = AdAccount(ad_account_id)
    results: dict[str, Any] = {}

    try:
        existing_ads = account.get_ads(
            fields=["id", "name", "creative"],
            params={"limit": 2},
        )
        creatives_detail = []
        for ad in existing_ads:
            creative_id = ad.get("creative", {}).get("id")
            if creative_id:
                from facebook_business.adobjects.adcreative import (
                    AdCreative,
                )

                creative = AdCreative(creative_id)
                creative_data = creative.api_get(fields=[
                    "id", "name", "body", "title",
                    "call_to_action_type", "image_hash", "image_url",
                    "object_story_spec", "object_url", "url_tags",
                    "instagram_actor_id", "status",
                ])
                # Convertir tous les champs en types sérialisables
                raw = {}
                for key in creative_data:
                    val = creative_data[key]
                    try:
                        raw[key] = (
                            dict(val)
                            if hasattr(val, "__iter__")
                            and not isinstance(val, str)
                            else val
                        )
                    except (TypeError, ValueError):
                        raw[key] = str(val)
                creatives_detail.append(raw)
        results["creative_details"] = creatives_detail
    except Exception as ex:
        results["error"] = str(ex)

    return [TextContent(type="text", text=json.dumps(
        results, ensure_ascii=False, indent=2))]
