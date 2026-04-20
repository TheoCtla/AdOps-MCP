"""Tool: google_ads_remove_negative_keyword.

Supprime un mot-clé négatif existant (niveau campagne ou ad group).
Opération irréversible.
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

TOOL_NAME = "google_ads_remove_negative_keyword"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Remove an existing negative keyword from a Google Ads campaign or ad group.\n"
        "\n"
        "Returns a JSON confirmation with success status, the level, criterion_id, and "
        "resource_name of the removed negative.\n"
        "\n"
        "Use this tool when a negative keyword is blocking relevant traffic and should be "
        "removed. Always verify the criterion_id with google_ads_get_negative_keywords before "
        "removing. Provide exactly one of campaign_id or ad_group_id to indicate the level.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Removing a negative keyword is IRREVERSIBLE — the "
        "keyword must be re-added manually if needed. Ads may immediately start showing for "
        "previously blocked searches."
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
            "criterion_id": {
                "type": "string",
                "description": (
                    "Numeric criterion ID of the negative keyword to remove. "
                    "Use google_ads_get_negative_keywords to find it."
                ),
            },
            "campaign_id": {
                "type": "string",
                "description": (
                    "Campaign ID if the negative is at campaign level. "
                    "Provide exactly one of campaign_id or ad_group_id."
                ),
            },
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Ad group ID if the negative is at ad group level. "
                    "Provide exactly one of campaign_id or ad_group_id."
                ),
            },
        },
        "required": ["customer_id", "criterion_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_remove_negative_keyword."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        criterion_id = numeric_id(args.get("criterion_id"), "criterion_id")
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not criterion_id:
        return error_payload("Paramètre 'criterion_id' requis.")

    if campaign_id and ad_group_id:
        return error_payload(
            "Fournir exactement UN des deux : campaign_id OU ad_group_id, pas les deux."
        )
    if not campaign_id and not ad_group_id:
        return error_payload(
            "Fournir campaign_id (niveau campagne) ou ad_group_id (niveau ad group)."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    if campaign_id:
        cc_op = operation.campaign_criterion_operation
        cc_op.remove = ga_service.campaign_criterion_path(
            customer_id, campaign_id, criterion_id,
        )
        level = "campaign"
    else:
        agc_op = operation.ad_group_criterion_operation
        agc_op.remove = ga_service.ad_group_criterion_path(
            customer_id, ad_group_id, criterion_id,
        )
        level = "ad_group"

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_remove_negative_keyword")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resp = response.mutate_operation_responses[0]
    if campaign_id:
        resource_name = resp.campaign_criterion_result.resource_name
    else:
        resource_name = resp.ad_group_criterion_result.resource_name

    payload = {
        "success": True,
        "action": "REMOVED_NEGATIVE",
        "level": level,
        "criterion_id": criterion_id,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
