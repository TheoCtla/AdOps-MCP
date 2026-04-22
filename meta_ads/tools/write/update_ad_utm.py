"""Tool: meta_ads_update_ad_utm.

Modifie les paramètres UTM d'une ad Meta.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_ad_utm"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the UTM parameters (url_tags) of a Meta Ads ad.\n"
        "\n"
        "Returns a JSON confirmation with the new url_tags.\n"
        "\n"
        "Use this tool to set or change UTM tracking parameters on an ad — e.g. "
        "'utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}'. Meta supports "
        "dynamic macros like {{campaign.name}}, {{adset.name}}, {{ad.name}}.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The UTM change takes effect immediately and impacts "
        "tracking on all future clicks."
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
            "url_tags": {
                "type": "string",
                "description": (
                    "UTM parameters string (e.g. "
                    "'utm_source=facebook&utm_medium=paid'). Pass empty "
                    "string to clear."
                ),
            },
        },
        "required": ["ad_account_id", "ad_id", "url_tags"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_ad_utm."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    ad_id = args.get("ad_id")
    url_tags = args.get("url_tags")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")
    if url_tags is None:
        return error_payload("Paramètre 'url_tags' requis.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.api import FacebookAdsApi

        api = FacebookAdsApi.get_default_api()
        resp = api.call(
            "POST", [ad_id], params={"url_tags": url_tags},
        ).json()

        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            return error_payload(
                f"Erreur Meta : {err.get('message', str(err))}"
            )
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_ad_utm")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "UPDATED_UTM",
        "ad_id": ad_id,
        "url_tags": url_tags,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
