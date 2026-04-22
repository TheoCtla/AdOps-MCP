"""Tool: meta_ads_create_lookalike_audience.

Crée une audience similaire (lookalike) à partir d'une audience source.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_create_lookalike_audience"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a lookalike audience based on an existing source audience on a Meta Ads "
        "account.\n"
        "\n"
        "Returns a JSON confirmation with the new audience_id, source, country, and ratio.\n"
        "\n"
        "Use this tool to find new people similar to an existing audience — e.g. a 1% "
        "lookalike of past converters in France. The ratio controls the trade-off between "
        "precision and reach: 0.01 (1%) = smallest and most similar, 0.10 (10%) = larger "
        "but less precise. Max 0.20 (20%). Use meta_ads_get_custom_audiences to find the "
        "origin_audience_id.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new lookalike audience is created on the account."
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
                "description": "Lookalike audience name.",
            },
            "origin_audience_id": {
                "type": "string",
                "description": (
                    "ID of the source audience. Use "
                    "meta_ads_get_custom_audiences to find it."
                ),
            },
            "country": {
                "type": "string",
                "description": (
                    "ISO country code for the lookalike (e.g. 'FR', 'BE', 'US')."
                ),
            },
            "ratio": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 0.20,
                "description": (
                    "Lookalike size: 0.01 = 1% most similar (precise), "
                    "0.10 = 10% (broad). Max 0.20."
                ),
            },
        },
        "required": ["ad_account_id", "name", "origin_audience_id", "country", "ratio"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_create_lookalike_audience."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    name = args.get("name")
    origin_audience_id = args.get("origin_audience_id")
    country = args.get("country")
    ratio_raw = args.get("ratio")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not name or not isinstance(name, str):
        return error_payload("Paramètre 'name' requis (texte non vide).")
    if not origin_audience_id:
        return error_payload("Paramètre 'origin_audience_id' requis.")
    if not country or not isinstance(country, str):
        return error_payload("Paramètre 'country' requis (code ISO, ex: 'FR').")

    try:
        ratio = float(ratio_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return error_payload("ratio doit être un nombre entre 0.01 et 0.20.")
    if not (0.01 <= ratio <= 0.20):
        return error_payload(
            f"Le ratio doit être entre 0.01 (1%) et 0.20 (20%). Reçu : {ratio}."
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
            CustomAudience.Field.subtype: "LOOKALIKE",
            CustomAudience.Field.origin_audience_id: origin_audience_id,
            CustomAudience.Field.lookalike_spec: {
                "ratio": ratio,
                "country": country.upper(),
            },
        }

        audience = account.create_custom_audience(params=params)
    except Exception as ex:
        log.exception("Erreur dans meta_ads_create_lookalike_audience")
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
        "action": "CREATED_LOOKALIKE",
        "audience_id": audience.get("id", ""),
        "name": name,
        "origin_audience_id": origin_audience_id,
        "country": country.upper(),
        "ratio": ratio,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
