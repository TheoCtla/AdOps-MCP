"""Tool: meta_ads_update_adset_targeting.

Remplace le ciblage complet d'un ad set Meta (âge, geo, intérêts,
audiences, etc.). C'est un remplacement total, pas incrémental.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_adset_targeting"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Replace the targeting of a Meta Ads ad set with a new targeting specification. "
        "This is a FULL REPLACEMENT — the entire targeting object is overwritten.\n"
        "\n"
        "Returns a JSON confirmation with the adset_id.\n"
        "\n"
        "Use this tool to change who sees ads in an ad set — e.g. narrow the age range, "
        "add interests, change geo, add/exclude custom audiences. The targeting object must "
        "include at minimum geo_locations. Use meta_ads_get_adset_performance to see current "
        "targeting before modifying.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The targeting change takes effect immediately and "
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
            "targeting": {
                "type": "object",
                "description": (
                    "Complete targeting spec. At minimum: "
                    "{\"geo_locations\": {\"countries\": [\"FR\"]}, "
                    "\"age_min\": 18, \"age_max\": 65}. Can include interests, "
                    "custom_audiences, excluded_custom_audiences, genders, etc."
                ),
            },
        },
        "required": ["ad_account_id", "adset_id", "targeting"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_adset_targeting."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")
    targeting = args.get("targeting")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")
    if not targeting or not isinstance(targeting, dict):
        return error_payload("Paramètre 'targeting' requis (objet JSON).")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adset import AdSet

        adset = AdSet(adset_id)
        adset[AdSet.Field.targeting] = targeting
        adset.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_adset_targeting")
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
        "action": "UPDATED_TARGETING",
        "adset_id": adset_id,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
