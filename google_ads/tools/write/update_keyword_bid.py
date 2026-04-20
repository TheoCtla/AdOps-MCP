"""Tool: google_ads_update_keyword_bid.

Modifie l'enchère CPC max d'un keyword existant. Sans effet réel sur les
campagnes smart bidding (Target CPA, Maximize Conversions, etc.).
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
    round_money,
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_update_keyword_bid"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the max CPC bid of an existing keyword in a Google Ads ad group.\n"
        "\n"
        "Returns a JSON confirmation with success status, the new CPC bid in euros, and the "
        "resource_name of the updated keyword.\n"
        "\n"
        "Use this tool to raise or lower the bid on a specific keyword — e.g. increase bid "
        "on a high-converting keyword, or decrease on a keyword with poor ROI. The bid is in "
        "euros and is automatically converted to micros. Note: on campaigns using smart "
        "bidding (Target CPA, Maximize Conversions, Target ROAS), the keyword-level CPC bid "
        "is ignored by Google — the mutation will succeed but won't affect the actual bid.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The bid change takes effect immediately and impacts "
        "live campaigns."
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
                    "Numeric criterion ID of the keyword to update. Use "
                    "google_ads_get_keywords to find it."
                ),
            },
            "new_cpc_bid": {
                "type": "number",
                "minimum": 0.01,
                "description": (
                    "New max CPC bid in euros (e.g. 1.50 for 1€50). "
                    "Automatically converted to micros for the API."
                ),
            },
        },
        "required": ["customer_id", "ad_group_id", "criterion_id", "new_cpc_bid"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_update_keyword_bid."""
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

    new_cpc_raw = args.get("new_cpc_bid")
    if new_cpc_raw is None:
        return error_payload("Paramètre 'new_cpc_bid' requis (en euros).")
    try:
        new_cpc_eur = float(new_cpc_raw)
    except (TypeError, ValueError):
        return error_payload("new_cpc_bid doit être un nombre (en euros).")
    if new_cpc_eur < 0.01:
        return error_payload("new_cpc_bid doit être >= 0.01€.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    agc_op = operation.ad_group_criterion_operation
    criterion = agc_op.update
    criterion.resource_name = ga_service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id,
    )
    criterion.cpc_bid_micros = int(new_cpc_eur * 1_000_000)
    client.copy_from(
        agc_op.update_mask,
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
        log.exception("Erreur inattendue dans google_ads_update_keyword_bid")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].ad_group_criterion_result.resource_name
    )

    payload = {
        "success": True,
        "action": "UPDATED_BID",
        "ad_group_id": ad_group_id,
        "criterion_id": criterion_id,
        "new_cpc_bid": round_money(new_cpc_eur),
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
