"""Tool: meta_ads_create_custom_audience.

Crée une audience personnalisée (retargeting site, engagement, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_create_custom_audience"

_ALLOWED_SUBTYPES = frozenset({
    "CUSTOM", "WEBSITE", "ENGAGEMENT", "OFFLINE_CONVERSION", "APP",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a custom audience on a Meta Ads account for retargeting: website visitors "
        "(pixel-based), engagement audiences, customer lists, or app users.\n"
        "\n"
        "Returns a JSON confirmation with the new audience_id.\n"
        "\n"
        "Use this tool to create retargeting audiences — e.g. visitors of a specific landing "
        "page (WEBSITE subtype with a URL rule), people who engaged with a page/video "
        "(ENGAGEMENT), or uploaded customer lists (CUSTOM). For WEBSITE subtype, provide a "
        "rule object with pixel ID, retention period, and URL filter. For CUSTOM subtype, "
        "provide customer_file_source. Use meta_ads_get_custom_audiences to see existing "
        "audiences.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new audience is created on the account."
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
            "name": {
                "type": "string",
                "description": "Audience name.",
            },
            "subtype": {
                "type": "string",
                "enum": list(_ALLOWED_SUBTYPES),
                "description": (
                    "Audience type: CUSTOM (customer list), WEBSITE (pixel), "
                    "ENGAGEMENT (page/video), OFFLINE_CONVERSION, APP."
                ),
            },
            "description": {
                "type": "string",
                "description": "Optional audience description.",
            },
            "rule": {
                "type": "object",
                "description": (
                    "Targeting rule for WEBSITE subtype. Include pixel ID, "
                    "retention_seconds, and URL filter."
                ),
            },
            "customer_file_source": {
                "type": "string",
                "enum": [
                    "USER_PROVIDED_ONLY",
                    "PARTNER_PROVIDED_ONLY",
                    "BOTH_USER_AND_PARTNER_PROVIDED",
                ],
                "description": "Required for CUSTOM subtype.",
            },
        },
        "required": ["ad_account_id", "name", "subtype"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_create_custom_audience."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    name = args.get("name")
    subtype = args.get("subtype")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not name or not isinstance(name, str):
        return error_payload("Paramètre 'name' requis (texte non vide).")
    if subtype not in _ALLOWED_SUBTYPES:
        return error_payload(
            f"subtype invalide : '{subtype}'. "
            f"Valeurs : {', '.join(sorted(_ALLOWED_SUBTYPES))}."
        )

    description = args.get("description")
    rule = args.get("rule")
    customer_file_source = args.get("customer_file_source")

    if subtype == "CUSTOM" and not customer_file_source:
        return error_payload(
            "customer_file_source requis quand subtype = 'CUSTOM'."
        )

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.adobjects.customaudience import CustomAudience

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            CustomAudience.Field.name: name,
            CustomAudience.Field.subtype: subtype,
        }
        if description:
            params[CustomAudience.Field.description] = description
        if rule:
            params[CustomAudience.Field.rule] = rule
        if customer_file_source:
            params[CustomAudience.Field.customer_file_source] = customer_file_source

        audience = account.create_custom_audience(params=params)
    except Exception as ex:
        log.exception("Erreur dans meta_ads_create_custom_audience")
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
        "action": "CREATED_CUSTOM_AUDIENCE",
        "audience_id": audience.get("id", ""),
        "name": name,
        "subtype": subtype,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
