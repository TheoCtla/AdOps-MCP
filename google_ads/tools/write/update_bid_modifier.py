"""Tool: google_ads_update_bid_modifier.

Modifie un ajustement d'enchère existant sur un campaign_criterion
(device, location, ad_schedule, audience, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from google.api_core import protobuf_helpers
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.helpers import (
    clean_customer_id,
    error_payload,
    format_google_ads_error,
    numeric_id,
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_update_bid_modifier"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update an existing bid modifier on a Google Ads campaign criterion (device, location, "
        "ad schedule, audience, age range, gender, etc.).\n"
        "\n"
        "Returns a JSON confirmation with success status, the new bid modifier value, and the "
        "resource_name.\n"
        "\n"
        "Use this tool to adjust bid multipliers — e.g. boost mobile bids by 20% (1.2), "
        "reduce tablet bids by 30% (0.7), or exclude a device entirely (0.0). Use "
        "google_ads_get_bid_modifiers to find the criterion_id. Values: 1.0 = neutral (no "
        "adjustment), >1.0 = boost, <1.0 = reduce, 0.0 = full exclusion.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The bid modifier change takes effect immediately and "
        "impacts live campaigns."
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
            "campaign_id": {
                "type": "string",
                "description": (
                    "Numeric campaign ID. Use "
                    "google_ads_get_campaign_performance to find it."
                ),
            },
            "criterion_id": {
                "type": "string",
                "description": (
                    "Numeric criterion ID to update. Use "
                    "google_ads_get_bid_modifiers to find it."
                ),
            },
            "new_bid_modifier": {
                "type": "number",
                "minimum": 0,
                "description": (
                    "New bid modifier value. 1.0 = neutral, 1.2 = +20%, "
                    "0.8 = -20%, 0.0 = exclusion."
                ),
            },
        },
        "required": ["customer_id", "campaign_id", "criterion_id", "new_bid_modifier"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_update_bid_modifier."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        criterion_id = numeric_id(args.get("criterion_id"), "criterion_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")
    if not criterion_id:
        return error_payload("Paramètre 'criterion_id' requis.")

    new_bid_raw = args.get("new_bid_modifier")
    if new_bid_raw is None:
        return error_payload("Paramètre 'new_bid_modifier' requis.")
    try:
        new_bid = float(new_bid_raw)
    except (TypeError, ValueError):
        return error_payload("new_bid_modifier doit être un nombre.")
    if new_bid < 0:
        return error_payload("new_bid_modifier doit être >= 0.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    cc_op = operation.campaign_criterion_operation
    criterion = cc_op.update
    criterion.resource_name = ga_service.campaign_criterion_path(
        customer_id, campaign_id, criterion_id,
    )
    criterion.bid_modifier = new_bid
    client.copy_from(
        cc_op.update_mask,
        protobuf_helpers.field_mask(None, criterion._pb),
    )

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_update_bid_modifier")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].campaign_criterion_result.resource_name
    )

    payload = {
        "success": True,
        "action": "UPDATED_BID_MODIFIER",
        "campaign_id": campaign_id,
        "criterion_id": criterion_id,
        "new_bid_modifier": round(new_bid, 2),
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
