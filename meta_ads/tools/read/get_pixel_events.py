"""Tool: meta_ads_get_pixel_events.

Liste les pixels du compte et leurs événements récents. Utile pour
vérifier que le tracking fonctionne.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_pixel_events"

_PIXEL_FIELDS = [
    "id", "name", "creation_time",
    "last_fired_time", "is_created_by_app",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List Meta pixels configured on an ad account and their recent events.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `total_pixels`, and `pixels` (array). "
        "Each entry contains: pixel_id, name, last_fired_time (null if never fired), "
        "creation_time, events (list of {event, count} — may be empty if stats are "
        "unavailable or the pixel has no recent activity). Some accounts have no pixels — "
        "that is normal.\n"
        "\n"
        "Use this tool to verify that tracking pixels are active, check when they last fired, "
        "or audit which conversion events are being tracked. No date range — pixel info is "
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
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_pixel_events."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        pixels_cursor = account.get_ads_pixels(fields=_PIXEL_FIELDS)

        results: list[dict[str, Any]] = []

        for pixel in pixels_cursor:
            if len(results) >= 20:
                break

            events: list[dict[str, Any]] = []
            try:
                stats = pixel.get_stats()
                for stat in stats:
                    data = stat.get("data")
                    if data:
                        for event_data in data:
                            events.append(
                                {
                                    "event": event_data.get("event"),
                                    "count": event_data.get("count"),
                                }
                            )
            except Exception:
                pass  # Stats unavailable — return empty events.

            results.append(
                {
                    "pixel_id": pixel["id"],
                    "name": pixel.get("name") or None,
                    "last_fired_time": pixel.get("last_fired_time") or None,
                    "creation_time": pixel.get("creation_time") or None,
                    "events": events,
                }
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_pixel_events")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "total_pixels": len(results),
        "pixels": results,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
