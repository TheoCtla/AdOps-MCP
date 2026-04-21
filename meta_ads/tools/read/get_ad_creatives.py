"""Tool: meta_ads_get_ad_creatives.

Liste complète des créas avec tous les détails (texte, image, vidéo,
CTA). Complète get_ad_performance qui ne retourne que les métriques.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_ad_creatives"

_CREATIVE_FIELDS = [
    "id", "name", "body", "title", "link_description",
    "call_to_action_type", "image_url", "image_hash",
    "video_id", "thumbnail_url", "object_url", "url_tags",
    "status",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List ad creatives on a Meta Ads account with full copy details: primary text, "
        "headline, description, CTA, image URL, video ID, destination URL, and URL tags.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `total_creatives`, and `creatives` "
        "(array). Each entry contains: creative_id, name, body (primary text), title "
        "(headline), link_description, cta (call_to_action_type), image_url, image_hash, "
        "video_id, thumbnail_url, destination_url, url_tags, status.\n"
        "\n"
        "Use this tool to audit ad copy, review creatives before launching, check image/video "
        "assets, or get the full copy that meta_ads_get_ad_performance doesn't include. "
        "No date range — creatives are account-level entities."
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
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Max creatives returned. Default: 25.",
                "default": 25,
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_ad_creatives."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    limit = min(int(args.get("limit", 25)), 100)

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        creatives_cursor = account.get_ad_creatives(
            fields=_CREATIVE_FIELDS, params={"limit": limit},
        )

        results: list[dict[str, Any]] = []
        truncated = False

        for creative in creatives_cursor:
            if len(results) >= limit:
                truncated = True
                break

            results.append(
                {
                    "creative_id": creative["id"],
                    "name": creative.get("name") or None,
                    "body": creative.get("body") or None,
                    "title": creative.get("title") or None,
                    "link_description": creative.get("link_description") or None,
                    "cta": creative.get("call_to_action_type") or None,
                    "image_url": creative.get("image_url") or None,
                    "image_hash": creative.get("image_hash") or None,
                    "video_id": creative.get("video_id") or None,
                    "thumbnail_url": creative.get("thumbnail_url") or None,
                    "destination_url": creative.get("object_url") or None,
                    "url_tags": creative.get("url_tags") or None,
                    "status": creative.get("status") or None,
                }
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_ad_creatives")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "total_creatives": len(results),
        "creatives": results,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
