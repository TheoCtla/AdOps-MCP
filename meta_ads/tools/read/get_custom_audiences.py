"""Tool: meta_ads_get_custom_audiences.

Liste les audiences personnalisées et lookalike du compte pub.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_custom_audiences"

_AUDIENCE_FIELDS = [
    "id", "name", "subtype",
    "approximate_count_lower_bound", "approximate_count_upper_bound",
    "lookalike_spec", "time_created", "time_updated",
    "description",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List custom audiences and lookalike audiences available on a Meta Ads account.\n"
        "\n"
        "Returns a JSON object with `ad_account_id`, `total_audiences`, and `audiences` "
        "(array). Each entry contains: audience_id, name, subtype (CUSTOM for customer lists, "
        "WEBSITE for pixel audiences, ENGAGEMENT for page/video interactions, LOOKALIKE for "
        "similar audiences, etc.), approximate_count (estimated size range e.g. "
        "'1000-1500', null if unavailable), "
        "lookalike_info (ratio, country, origin_id — only for lookalike audiences, null "
        "otherwise), description, time_created, time_updated. No date range — audiences are "
        "account-level entities.\n"
        "\n"
        "Use this tool to discover which audiences are available for targeting, check audience "
        "sizes, audit lookalike configurations, or find audiences to add/exclude on campaigns."
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
                "maximum": 200,
                "description": "Max audiences returned. Default: 50.",
                "default": 50,
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_custom_audiences."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    limit = min(int(args.get("limit", 50)), 200)

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        audiences_cursor = account.get_custom_audiences(
            fields=_AUDIENCE_FIELDS, params={"limit": limit},
        )

        results: list[dict[str, Any]] = []
        truncated = False

        for aud in audiences_cursor:
            if len(results) >= limit:
                truncated = True
                break

            lookalike_info = None
            spec = aud.get("lookalike_spec")
            if spec:
                origin = spec.get("origin")
                lookalike_info = {
                    "ratio": spec.get("ratio"),
                    "country": spec.get("country"),
                    "origin_id": origin[0].get("id") if origin else None,
                }

            lower = aud.get("approximate_count_lower_bound")
            upper = aud.get("approximate_count_upper_bound")
            approx = f"{lower}-{upper}" if lower is not None and upper is not None else None

            results.append(
                {
                    "audience_id": aud["id"],
                    "name": aud.get("name"),
                    "subtype": aud.get("subtype"),
                    "approximate_count": approx,
                    "lookalike_info": lookalike_info,
                    "description": aud.get("description") or None,
                    "time_created": aud.get("time_created"),
                    "time_updated": aud.get("time_updated"),
                }
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_custom_audiences")
        return error_payload(format_meta_error(ex))

    payload = {
        "ad_account_id": ad_account_id,
        "total_audiences": len(results),
        "audiences": results,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
