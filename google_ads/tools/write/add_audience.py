"""Tool: google_ads_add_audience.

Ajoute un segment d'audience à une campagne (targeting ou observation)
avec un bid modifier optionnel.
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

TOOL_NAME = "google_ads_add_audience"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Add an audience segment (user list) to a Google Ads campaign for targeting or "
        "observation, with an optional bid modifier.\n"
        "\n"
        "Returns a JSON confirmation with success status, the user_list_id, bid_modifier, "
        "and resource_name.\n"
        "\n"
        "Use this tool to layer an audience onto a campaign — e.g. target past converters "
        "with a bid boost, or add a remarketing list for observation. Use "
        "google_ads_get_audiences to see existing audience segments.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The audience is added to the campaign immediately and "
        "impacts ad delivery and bidding."
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
                "description": "Numeric campaign ID.",
            },
            "user_list_id": {
                "type": "string",
                "description": "Numeric user list (audience) ID.",
            },
            "bid_modifier": {
                "type": "number",
                "minimum": 0,
                "description": (
                    "Optional bid multiplier. 1.0 = neutral, 1.5 = +50%. "
                    "If omitted, no bid adjustment is applied."
                ),
            },
        },
        "required": ["customer_id", "campaign_id", "user_list_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_add_audience."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        user_list_id = numeric_id(args.get("user_list_id"), "user_list_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")
    if not user_list_id:
        return error_payload("Paramètre 'user_list_id' requis.")

    bid_mod_raw = args.get("bid_modifier")
    bid_mod: float | None = None
    if bid_mod_raw is not None:
        try:
            bid_mod = float(bid_mod_raw)
        except (TypeError, ValueError):
            return error_payload("bid_modifier doit être un nombre.")
        if bid_mod < 0:
            return error_payload("bid_modifier doit être >= 0.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    cc_op = operation.campaign_criterion_operation
    criterion = cc_op.create
    criterion.campaign = ga_service.campaign_path(customer_id, campaign_id)
    criterion.user_list.user_list = (
        f"customers/{customer_id}/userLists/{user_list_id}"
    )
    if bid_mod is not None:
        criterion.bid_modifier = bid_mod

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_add_audience")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].campaign_criterion_result.resource_name
    )

    payload = {
        "success": True,
        "action": "ADDED_AUDIENCE",
        "campaign_id": campaign_id,
        "user_list_id": user_list_id,
        "bid_modifier": round(bid_mod, 2) if bid_mod is not None else None,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
