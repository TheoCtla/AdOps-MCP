"""Tool: google_ads_enable_ad_group.

Réactive un ad group en pause. Reprend la diffusion de ses annonces.
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

TOOL_NAME = "google_ads_enable_ad_group"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Enable (reactivate) a paused Google Ads ad group, immediately resuming ad delivery "
        "for all ads in that group.\n"
        "\n"
        "Returns a JSON confirmation with success status, action taken, and the resource name.\n"
        "\n"
        "Use this tool when the user wants to reactivate a previously paused ad group.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Enabling an ad group resumes ad delivery immediately "
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
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Numeric ad group ID to enable. Use "
                    "google_ads_get_adgroup_performance to find it."
                ),
            },
        },
        "required": ["customer_id", "ad_group_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_enable_ad_group."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not ad_group_id:
        return error_payload("Paramètre 'ad_group_id' requis.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    operation = client.get_type("MutateOperation")
    ag_op = operation.ad_group_operation
    ad_group = ag_op.update
    ad_group.resource_name = ga_service.ad_group_path(customer_id, ad_group_id)
    ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
    client.copy_from(
        ag_op.update_mask,
        protobuf_helpers.field_mask(None, ad_group._pb),
    )

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_enable_ad_group")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].ad_group_result.resource_name
    )

    payload = {
        "success": True,
        "action": "ENABLED",
        "resource": "ad_group",
        "ad_group_id": ad_group_id,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
