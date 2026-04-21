"""Tool: meta_ads_get_creative_asset_details.

Détails des fichiers média (images et vidéos) du compte avec URLs et
métadonnées. Audit de la bibliothèque de créas.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_creative_asset_details"

_ALLOWED_ASSET_TYPES = frozenset({"IMAGE", "VIDEO", "ALL"})

_IMAGE_FIELDS = [
    "hash", "name", "url", "url_128",
    "width", "height", "created_time", "status",
]

_VIDEO_FIELDS = [
    "id", "title", "description", "length",
    "picture", "source", "created_time", "status",
    "updated_time",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List image and video assets in a Meta Ads account's creative library with URLs "
        "and metadata.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `filters`, `total_images`, "
        "`total_videos`, `images` (array), and `videos` (array). Image entries contain: "
        "type, hash, name, url, thumbnail_url, width, height, created_time. Video entries "
        "contain: type, video_id, title, description, length (seconds), thumbnail_url, "
        "source_url, created_time.\n"
        "\n"
        "Use this tool to audit the creative library, check available images/videos, find "
        "asset URLs for reporting, or verify that uploaded assets are present. Filter by "
        "asset_type to see only images or only videos. No date range — assets are "
        "account-level."
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
            "asset_type": {
                "type": "string",
                "enum": ["IMAGE", "VIDEO", "ALL"],
                "description": "Filter by asset type. Default: ALL.",
                "default": "ALL",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Max assets per type returned. Default: 25.",
                "default": 25,
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_creative_asset_details."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    asset_type = (args.get("asset_type") or "ALL").upper()
    if asset_type not in _ALLOWED_ASSET_TYPES:
        return error_payload(
            f"asset_type invalide : '{asset_type}'. Valeurs : IMAGE, VIDEO, ALL."
        )

    limit = min(int(args.get("limit", 25)), 100)

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        image_results: list[dict[str, Any]] = []
        video_results: list[dict[str, Any]] = []

        if asset_type in ("IMAGE", "ALL"):
            images_cursor = account.get_ad_images(fields=_IMAGE_FIELDS)
            for img in images_cursor:
                if len(image_results) >= limit:
                    break
                image_results.append(
                    {
                        "type": "IMAGE",
                        "hash": img.get("hash"),
                        "name": img.get("name") or None,
                        "url": img.get("url") or None,
                        "thumbnail_url": img.get("url_128") or None,
                        "width": img.get("width"),
                        "height": img.get("height"),
                        "created_time": img.get("created_time") or None,
                    }
                )

        if asset_type in ("VIDEO", "ALL"):
            videos_cursor = account.get_ad_videos(fields=_VIDEO_FIELDS)
            for vid in videos_cursor:
                if len(video_results) >= limit:
                    break
                video_results.append(
                    {
                        "type": "VIDEO",
                        "video_id": vid.get("id"),
                        "title": vid.get("title") or None,
                        "description": vid.get("description") or None,
                        "length": vid.get("length"),
                        "thumbnail_url": vid.get("picture") or None,
                        "source_url": vid.get("source") or None,
                        "created_time": vid.get("created_time") or None,
                    }
                )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_creative_asset_details")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "filters": {"asset_type": asset_type},
        "total_images": len(image_results),
        "total_videos": len(video_results),
        "images": image_results,
        "videos": video_results,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
