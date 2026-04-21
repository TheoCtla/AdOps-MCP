"""Tool: google_ads_create_sitelink.

Crée un sitelink asset et optionnellement le lie à une campagne.
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

TOOL_NAME = "google_ads_create_sitelink"

_LINK_TEXT_MAX = 25
_DESC_MAX = 35


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a sitelink extension (asset) on a Google Ads account and optionally link it "
        "to a specific campaign.\n"
        "\n"
        "Returns a JSON confirmation with the asset_resource_name and whether it was linked "
        "to a campaign.\n"
        "\n"
        "Use this tool to add sitelinks (additional links below the main ad). Constraints: "
        "link_text max 25 chars, description1/description2 max 35 chars each. Pass "
        "campaign_id to link the sitelink to a specific campaign; omit to create an "
        "account-level asset that can be linked later.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new sitelink asset is created and optionally linked "
        "to a campaign. The sitelink becomes eligible to show immediately if linked to an "
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
            "link_text": {
                "type": "string",
                "description": f"Sitelink text (max {_LINK_TEXT_MAX} chars).",
            },
            "final_url": {
                "type": "string",
                "description": "Landing page URL (must start with http:// or https://).",
            },
            "description1": {
                "type": "string",
                "description": f"Optional first description line (max {_DESC_MAX} chars).",
            },
            "description2": {
                "type": "string",
                "description": f"Optional second description line (max {_DESC_MAX} chars).",
            },
            "campaign_id": {
                "type": "string",
                "description": (
                    "Optional campaign ID to link the sitelink to. If omitted, "
                    "the sitelink is created at account level."
                ),
            },
        },
        "required": ["customer_id", "link_text", "final_url"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_create_sitelink."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    link_text = args.get("link_text", "")
    if not isinstance(link_text, str) or not link_text.strip():
        return error_payload("Paramètre 'link_text' requis (texte non vide).")
    link_text = link_text.strip()
    if len(link_text) > _LINK_TEXT_MAX:
        return error_payload(
            f"link_text trop long ({len(link_text)} chars, max {_LINK_TEXT_MAX})."
        )

    final_url = args.get("final_url", "")
    if not isinstance(final_url, str) or not final_url.startswith(("http://", "https://")):
        return error_payload("final_url doit commencer par http:// ou https://.")

    desc1 = (args.get("description1") or "").strip()
    desc2 = (args.get("description2") or "").strip()
    if desc1 and len(desc1) > _DESC_MAX:
        return error_payload(f"description1 trop long ({len(desc1)} chars, max {_DESC_MAX}).")
    if desc2 and len(desc2) > _DESC_MAX:
        return error_payload(f"description2 trop long ({len(desc2)} chars, max {_DESC_MAX}).")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    # Step 1: create the sitelink asset.
    operation = client.get_type("MutateOperation")
    asset_op = operation.asset_operation
    asset = asset_op.create
    asset.sitelink_asset.link_text = link_text
    asset.sitelink_asset.description1 = desc1
    asset.sitelink_asset.description2 = desc2
    asset.final_urls.append(final_url)

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_create_sitelink (asset)")
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
        ca.field_type = client.enums.AssetFieldTypeEnum.SITELINK

        try:
            ga_service.mutate(
                customer_id=customer_id,
                mutate_operations=[op2],
            )
            linked_to = campaign_id
        except GoogleAdsException as ex:
            return error_payload(
                f"Sitelink créé ({asset_resource_name}) mais échec du lien à la "
                f"campagne : {format_google_ads_error(ex)}"
            )

    payload = {
        "success": True,
        "action": "CREATED_SITELINK",
        "link_text": link_text,
        "final_url": final_url,
        "asset_resource_name": asset_resource_name,
        "linked_to_campaign": linked_to,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
