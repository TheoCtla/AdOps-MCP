"""Tool: google_ads_pause_campaign.

Met en pause une campagne Google Ads. Stoppe immédiatement la diffusion
de toutes les annonces de cette campagne.
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

TOOL_NAME = "google_ads_pause_campaign"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Pause a Google Ads campaign, immediately stopping all ad delivery for that campaign.\n"
        "\n"
        "Returns a JSON confirmation with success status, action taken, and the resource name "
        "of the modified campaign. Use google_ads_enable_campaign to reactivate a paused "
        "campaign.\n"
        "\n"
        "Use this tool when the user wants to stop a campaign from spending, needs to pause "
        "delivery while making changes, or identifies a campaign that should be stopped "
        "urgently.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Pausing a campaign stops all ad delivery immediately "
        "and impacts live campaigns."
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
                    "Numeric campaign ID to pause. Use "
                    "google_ads_get_campaign_performance to find it."
                ),
            },
        },
        "required": ["customer_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_pause_campaign."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    operation = client.get_type("MutateOperation")
    campaign_op = operation.campaign_operation
    campaign = campaign_op.update
    campaign.resource_name = ga_service.campaign_path(customer_id, campaign_id)
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    client.copy_from(
        campaign_op.update_mask,
        protobuf_helpers.field_mask(None, campaign._pb),
    )

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_pause_campaign")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].campaign_result.resource_name
    )

    payload = {
        "success": True,
        "action": "PAUSED",
        "resource": "campaign",
        "campaign_id": campaign_id,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
