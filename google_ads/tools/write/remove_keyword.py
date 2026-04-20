"""Tool: google_ads_remove_keyword.

Supprime un mot-clé positif d'un ad group. Opération irréversible —
préférer pause_keyword quand possible.
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

TOOL_NAME = "google_ads_remove_keyword"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Permanently remove a keyword from a Google Ads ad group.\n"
        "\n"
        "Returns a JSON confirmation with success status, ad_group_id, criterion_id, and the "
        "resource_name of the removed keyword.\n"
        "\n"
        "Use this tool only when a keyword should be permanently deleted (not just paused). "
        "Prefer google_ads_pause_keyword when the keyword might be reactivated later — "
        "removal is IRREVERSIBLE.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Removing a keyword is IRREVERSIBLE — it must be "
        "re-created manually if needed. The ad group immediately stops being eligible for "
        "that keyword's search queries."
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
                    "Numeric ad group ID containing the keyword. Use "
                    "google_ads_get_keywords to find it."
                ),
            },
            "criterion_id": {
                "type": "string",
                "description": (
                    "Numeric criterion ID of the keyword to remove. Use "
                    "google_ads_get_keywords to find it."
                ),
            },
        },
        "required": ["customer_id", "ad_group_id", "criterion_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_remove_keyword."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
        criterion_id = numeric_id(args.get("criterion_id"), "criterion_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not ad_group_id:
        return error_payload("Paramètre 'ad_group_id' requis.")
    if not criterion_id:
        return error_payload("Paramètre 'criterion_id' requis.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    agc_op = operation.ad_group_criterion_operation
    agc_op.remove = ga_service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id,
    )

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_remove_keyword")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].ad_group_criterion_result.resource_name
    )

    payload = {
        "success": True,
        "action": "REMOVED_KEYWORD",
        "ad_group_id": ad_group_id,
        "criterion_id": criterion_id,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
