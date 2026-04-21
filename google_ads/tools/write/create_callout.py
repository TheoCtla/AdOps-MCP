"""Tool: google_ads_create_callout.

Crée un callout asset et optionnellement le lie à une campagne.
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

TOOL_NAME = "google_ads_create_callout"

_CALLOUT_MAX = 25


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a callout extension (asset) on a Google Ads account and optionally link it "
        "to a specific campaign.\n"
        "\n"
        "Returns a JSON confirmation with the asset_resource_name and whether it was linked "
        "to a campaign.\n"
        "\n"
        "Use this tool to add callouts (short highlight phrases like 'Free Shipping', "
        "'24/7 Support', 'Devis Gratuit'). Max 25 characters. Pass campaign_id to link "
        "the callout to a specific campaign; omit to create an account-level asset.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new callout asset is created and optionally linked "
        "to a campaign. The callout becomes eligible to show immediately if linked to an "
        "active campaign."
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
            "callout_text": {
                "type": "string",
                "description": f"Callout text (max {_CALLOUT_MAX} chars).",
            },
            "campaign_id": {
                "type": "string",
                "description": (
                    "Optional campaign ID to link the callout to. If omitted, "
                    "the callout is created at account level."
                ),
            },
        },
        "required": ["customer_id", "callout_text"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_create_callout."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    callout_text = args.get("callout_text", "")
    if not isinstance(callout_text, str) or not callout_text.strip():
        return error_payload("Paramètre 'callout_text' requis (texte non vide).")
    callout_text = callout_text.strip()
    if len(callout_text) > _CALLOUT_MAX:
        return error_payload(
            f"callout_text trop long ({len(callout_text)} chars, max {_CALLOUT_MAX})."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    # Step 1: create the callout asset.
    operation = client.get_type("MutateOperation")
    asset_op = operation.asset_operation
    asset = asset_op.create
    asset.callout_asset.callout_text = callout_text

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_create_callout (asset)")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    asset_resource_name = (
        response.mutate_operation_responses[0].asset_result.resource_name
    )

    # Step 2: optionally link to a campaign.
    linked_to = None
    if campaign_id:
        op2 = client.get_type("MutateOperation")
        ca_op = op2.campaign_asset_operation
        ca = ca_op.create
        ca.campaign = ga_service.campaign_path(customer_id, campaign_id)
        ca.asset = asset_resource_name
        ca.field_type = client.enums.AssetFieldTypeEnum.CALLOUT

        try:
            ga_service.mutate(
                customer_id=customer_id,
                mutate_operations=[op2],
            )
            linked_to = campaign_id
        except GoogleAdsException as ex:
            return error_payload(
                f"Callout créé ({asset_resource_name}) mais échec du lien à la "
                f"campagne : {format_google_ads_error(ex)}"
            )

    payload = {
        "success": True,
        "action": "CREATED_CALLOUT",
        "callout_text": callout_text,
        "asset_resource_name": asset_resource_name,
        "linked_to_campaign": linked_to,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
