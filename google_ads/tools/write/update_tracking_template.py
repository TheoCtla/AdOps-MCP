"""Tool: google_ads_update_tracking_template.

Modifie le tracking template au niveau account, campaign ou ad group.
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

TOOL_NAME = "google_ads_update_tracking_template"

_ALLOWED_LEVELS = frozenset({"ACCOUNT", "CAMPAIGN", "AD_GROUP"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the tracking URL template on a Google Ads account, campaign, or ad group.\n"
        "\n"
        "Returns a JSON confirmation with the level, resource, and the new tracking template.\n"
        "\n"
        "Use this tool to set or change the tracking template that appends UTM parameters or "
        "third-party click trackers to ad URLs. The template uses ValueTrack parameters like "
        "{lpurl}, {campaignid}, {keyword}, etc. Set at ACCOUNT level for global tracking, or "
        "at CAMPAIGN/AD_GROUP level for specific overrides. Pass an empty string to clear the "
        "template.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The tracking template change takes effect immediately "
        "and impacts all ad clicks on the affected level."
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
            "level": {
                "type": "string",
                "enum": ["ACCOUNT", "CAMPAIGN", "AD_GROUP"],
                "description": "Level to set the tracking template on.",
            },
            "resource_id": {
                "type": "string",
                "description": (
                    "Campaign or ad group ID. Required when level is CAMPAIGN "
                    "or AD_GROUP. Ignored for ACCOUNT."
                ),
            },
            "tracking_template": {
                "type": "string",
                "description": (
                    "The tracking URL template "
                    "(e.g. '{lpurl}?utm_source=google&utm_medium=cpc'). "
                    "Pass empty string to clear."
                ),
            },
        },
        "required": ["customer_id", "level", "tracking_template"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_update_tracking_template."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        resource_id = numeric_id(args.get("resource_id"), "resource_id")
    except ValueError as ex:
        return error_payload(str(ex))

    level = args.get("level")
    if level not in _ALLOWED_LEVELS:
        return error_payload(
            f"level invalide : '{level}'. Valeurs : {', '.join(sorted(_ALLOWED_LEVELS))}."
        )

    if level in ("CAMPAIGN", "AD_GROUP") and not resource_id:
        return error_payload(f"resource_id requis quand level = '{level}'.")

    tracking_template = args.get("tracking_template")
    if tracking_template is None:
        return error_payload("Paramètre 'tracking_template' requis.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    if level == "ACCOUNT":
        cust_op = operation.customer_operation
        customer = cust_op.update
        customer.resource_name = f"customers/{customer_id}"
        customer.tracking_url_template = tracking_template
        client.copy_from(
            cust_op.update_mask,
            protobuf_helpers.field_mask(None, customer._pb),
        )
    elif level == "CAMPAIGN":
        camp_op = operation.campaign_operation
        campaign = camp_op.update
        campaign.resource_name = ga_service.campaign_path(customer_id, resource_id)
        campaign.tracking_url_template = tracking_template
        client.copy_from(
            camp_op.update_mask,
            protobuf_helpers.field_mask(None, campaign._pb),
        )
    else:  # AD_GROUP
        ag_op = operation.ad_group_operation
        ad_group = ag_op.update
        ad_group.resource_name = ga_service.ad_group_path(customer_id, resource_id)
        ad_group.tracking_url_template = tracking_template
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
        log.exception("Erreur inattendue dans google_ads_update_tracking_template")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resp = response.mutate_operation_responses[0]
    if level == "ACCOUNT":
        res_name = resp.customer_result.resource_name
    elif level == "CAMPAIGN":
        res_name = resp.campaign_result.resource_name
    else:
        res_name = resp.ad_group_result.resource_name

    payload = {
        "success": True,
        "action": "UPDATED_TRACKING_TEMPLATE",
        "level": level,
        "resource_id": resource_id or None,
        "tracking_template": tracking_template,
        "resource_name": res_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
