"""Tool: google_ads_exclude_audience.

Exclut un segment d'audience d'une campagne — les utilisateurs de cette
liste ne verront plus les ads.
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

TOOL_NAME = "google_ads_exclude_audience"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Exclude an audience segment (user list) from a Google Ads campaign — users in this "
        "list will no longer see ads from this campaign.\n"
        "\n"
        "Returns a JSON confirmation with success status, user_list_id, and resource_name.\n"
        "\n"
        "Use this tool to exclude existing customers, recent converters, or any audience that "
        "should not be targeted by a specific campaign. Use google_ads_get_audiences to see "
        "current audience segments.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The audience exclusion takes effect immediately and "
        "prevents matched users from seeing ads on this campaign."
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
                "description": "Numeric user list (audience) ID to exclude.",
            },
        },
        "required": ["customer_id", "campaign_id", "user_list_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_exclude_audience."""
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
    criterion.negative = True

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_exclude_audience")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].campaign_criterion_result.resource_name
    )

    payload = {
        "success": True,
        "action": "EXCLUDED_AUDIENCE",
        "campaign_id": campaign_id,
        "user_list_id": user_list_id,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
