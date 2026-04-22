"""Tool: meta_ads_update_adset_schedule.

Modifie les dates de début et/ou fin d'un ad set Meta.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_adset_schedule"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the start and/or end time of a Meta Ads ad set.\n"
        "\n"
        "Returns a JSON confirmation with the updated times.\n"
        "\n"
        "Use this tool to change when an ad set starts or stops running — e.g. extend an "
        "end date, schedule a future launch, or set a hard stop. Times must be in ISO 8601 "
        "format (e.g. '2026-05-01T00:00:00+0200'). At least one of start_time or end_time "
        "must be provided.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The schedule change takes effect immediately."
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
            "start_time": {
                "type": "string",
                "description": "New start time (ISO 8601). Optional.",
            },
            "end_time": {
                "type": "string",
                "description": "New end time (ISO 8601). Optional.",
            },
        },
        "required": ["ad_account_id", "adset_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_adset_schedule."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")
    start_time = args.get("start_time")
    end_time = args.get("end_time")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")
    if not start_time and not end_time:
        return error_payload(
            "Au moins un paramètre requis : start_time ou end_time."
        )

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adset import AdSet

        adset = AdSet(adset_id)
        if start_time:
            adset[AdSet.Field.start_time] = start_time
        if end_time:
            adset[AdSet.Field.end_time] = end_time
        adset.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_adset_schedule")
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
        "action": "UPDATED_SCHEDULE",
        "adset_id": adset_id,
        "start_time": start_time,
        "end_time": end_time,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
