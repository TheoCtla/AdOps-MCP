"""Tool: meta_ads_update_adset_placements.

Modifie les placements d'un ad set Meta (où les ads sont diffusées).
Merge les placements dans le targeting existant sans toucher au reste.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_adset_placements"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the placements of a Meta Ads ad set — where ads are shown (Facebook Feed, "
        "Instagram Stories, Reels, etc.). This merges placement settings into the existing "
        "targeting without changing other targeting parameters (age, geo, interests).\n"
        "\n"
        "Returns a JSON confirmation with the updated publisher_platforms.\n"
        "\n"
        "Use this tool to control where ads appear — e.g. restrict to Instagram only, remove "
        "Audience Network, or add Reels. At minimum provide publisher_platforms. Use "
        "meta_ads_get_placement_performance to see which placements perform best.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The placement change takes effect immediately and "
        "impacts ad delivery."
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
                "description": "Numeric ad set ID to update.",
            },
            "publisher_platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Platforms to serve on: facebook, instagram, "
                    "audience_network, messenger."
                ),
            },
            "facebook_positions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Facebook positions: feed, right_hand_column, marketplace, "
                    "video_feeds, story, search, instream_video, reels."
                ),
            },
            "instagram_positions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Instagram positions: stream, story, explore, reels, shop."
                ),
            },
        },
        "required": ["ad_account_id", "adset_id", "publisher_platforms"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_adset_placements."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")
    publisher_platforms = args.get("publisher_platforms")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")
    if not publisher_platforms or not isinstance(publisher_platforms, list):
        return error_payload("Paramètre 'publisher_platforms' requis (tableau).")

    facebook_positions = args.get("facebook_positions")
    instagram_positions = args.get("instagram_positions")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adset import AdSet

        adset = AdSet(adset_id)

        # Fetch current targeting to merge placements into it.
        adset_data = adset.api_get(fields=["targeting"])
        current_targeting = adset_data.get("targeting", {}) or {}

        current_targeting["publisher_platforms"] = publisher_platforms
        if facebook_positions:
            current_targeting["facebook_positions"] = facebook_positions
        if instagram_positions:
            current_targeting["instagram_positions"] = instagram_positions

        adset[AdSet.Field.targeting] = current_targeting
        adset.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_adset_placements")
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
        "action": "UPDATED_PLACEMENTS",
        "adset_id": adset_id,
        "publisher_platforms": publisher_platforms,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
