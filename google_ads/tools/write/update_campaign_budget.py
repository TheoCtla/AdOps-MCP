"""Tool: google_ads_update_campaign_budget.

Modifie le budget quotidien d'une campagne. Récupère d'abord le
resource_name du CampaignBudget lié, puis le mute.
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
from google_ads.queries import CAMPAIGN_BUDGET_LOOKUP_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_update_campaign_budget"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the daily budget of a Google Ads campaign.\n"
        "\n"
        "Returns a JSON confirmation with success status, the new daily budget in euros, and "
        "the budget resource_name.\n"
        "\n"
        "Use this tool when the user asks to increase or decrease a campaign's daily spend. "
        "The budget is in euros and is automatically converted to micros. Note: if the budget "
        "is shared across multiple campaigns (shared budget), ALL linked campaigns will be "
        "affected.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The budget change takes effect immediately and impacts "
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
            "campaign_id": {
                "type": "string",
                "description": (
                    "Numeric campaign ID. Use "
                    "google_ads_get_campaign_performance to find it."
                ),
            },
            "new_daily_budget": {
                "type": "number",
                "minimum": 0.01,
                "description": (
                    "New daily budget in euros (e.g. 50.00 for 50€/day). "
                    "Automatically converted to micros for the API."
                ),
            },
        },
        "required": ["customer_id", "campaign_id", "new_daily_budget"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_update_campaign_budget."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

    new_budget_raw = args.get("new_daily_budget")
    if new_budget_raw is None:
        return error_payload("Paramètre 'new_daily_budget' requis (en euros).")
    try:
        new_budget_eur = float(new_budget_raw)
    except (TypeError, ValueError):
        return error_payload("new_daily_budget doit être un nombre (en euros).")
    if new_budget_eur < 0.01:
        return error_payload("new_daily_budget doit être >= 0.01€.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    # Step 1: lookup the budget resource_name linked to this campaign.
    query = CAMPAIGN_BUDGET_LOOKUP_QUERY.format(campaign_id=campaign_id)
    try:
        lookup_resp = ga_service.search(customer_id=customer_id, query=query)
        rows = list(lookup_resp)
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))

    if not rows:
        return error_payload(
            f"Aucune campagne trouvée avec campaign_id={campaign_id} "
            f"sur le compte {customer_id}."
        )

    budget_resource_name = rows[0].campaign_budget.resource_name

    # Step 2: mutate the budget.
    operation = client.get_type("MutateOperation")
    budget_op = operation.campaign_budget_operation
    budget = budget_op.update
    budget.resource_name = budget_resource_name
    budget.amount_micros = int(new_budget_eur * 1_000_000)
    client.copy_from(
        budget_op.update_mask,
        protobuf_helpers.field_mask(None, budget._pb),
    )

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_update_campaign_budget")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    payload = {
        "success": True,
        "action": "UPDATED_BUDGET",
        "campaign_id": campaign_id,
        "new_daily_budget": round_money(new_budget_eur),
        "budget_resource_name": budget_resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
