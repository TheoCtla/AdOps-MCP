"""Tool: google_ads_remove_ad.

Supprime définitivement une annonce. Opération irréversible — préférer
pause_ad quand possible.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.helpers import (
    clean_customer_id,
    error_payload,
    format_google_ads_error,
    numeric_id,
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_remove_ad"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Permanently remove an ad from a Google Ads ad group.\n"
        "\n"
        "Returns a JSON confirmation with success status, ad_group_id, ad_id, and the "
        "resource_name of the removed ad.\n"
        "\n"
        "Use this tool only when an ad should be permanently deleted. Prefer "
        "google_ads_pause_ad when the ad might be reactivated later — removal is "
        "IRREVERSIBLE.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Removing an ad is IRREVERSIBLE — it must be "
        "re-created manually if needed. The ad immediately stops serving."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": (
                    "Google Ads client account ID (10 digits). "
                    "Use google_ads_list_accounts first to find it."
                ),
            },
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Numeric ad group ID containing the ad. Use "
                    "google_ads_get_ads to find it."
                ),
            },
            "ad_id": {
                "type": "string",
                "description": (
                    "Numeric ad ID to remove. Use google_ads_get_ads to find it."
                ),
            },
        },
        "required": ["customer_id", "ad_group_id", "ad_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_remove_ad."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
        ad_id = numeric_id(args.get("ad_id"), "ad_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not ad_group_id:
        return error_payload("Paramètre 'ad_group_id' requis.")
    if not ad_id:
        return error_payload("Paramètre 'ad_id' requis.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    ad_group_ad_op = operation.ad_group_ad_operation
    ad_group_ad_op.remove = ga_service.ad_group_ad_path(
        customer_id, ad_group_id, ad_id,
    )

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_remove_ad")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].ad_group_ad_result.resource_name
    )

    payload = {
        "success": True,
        "action": "REMOVED_AD",
        "ad_group_id": ad_group_id,
        "ad_id": ad_id,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
