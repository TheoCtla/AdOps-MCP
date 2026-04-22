"""Tool: meta_ads_update_campaign_budget.

Modifie le budget d'une campagne Meta Ads (daily ou lifetime).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, euros_to_cents, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_campaign_budget"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the budget of a Meta Ads campaign (daily or lifetime). Provide exactly one "
        "of daily_budget or lifetime_budget — you cannot mix budget types on the same "
        "campaign.\n"
        "\n"
        "Returns a JSON confirmation with the new budget value in euros.\n"
        "\n"
        "Use this tool when the user asks to increase or decrease a campaign's budget. "
        "The value is in euros and is automatically converted to centimes for the API.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The budget change takes effect immediately and "
        "impacts live campaigns."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "ad_account_id": {
                "type": "string",
                "description": (
                    "Meta ad account ID (format 'act_XXXXX'). "
                    "Use meta_ads_list_ad_accounts to find it."
                ),
            },
            "campaign_id": {
                "type": "string",
                "description": "Numeric campaign ID.",
            },
            "daily_budget": {
                "type": "number",
                "minimum": 1,
                "description": (
                    "New daily budget in euros. Provide this OR "
                    "lifetime_budget, not both."
                ),
            },
            "lifetime_budget": {
                "type": "number",
                "minimum": 1,
                "description": (
                    "New lifetime budget in euros. Provide this OR "
                    "daily_budget, not both."
                ),
            },
        },
        "required": ["ad_account_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_campaign_budget."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    campaign_id = args.get("campaign_id")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

    daily_raw = args.get("daily_budget")
    lifetime_raw = args.get("lifetime_budget")

    if daily_raw is not None and lifetime_raw is not None:
        return error_payload(
            "Fournir exactement UN des deux : daily_budget OU lifetime_budget."
        )
    if daily_raw is None and lifetime_raw is None:
        return error_payload(
            "Fournir daily_budget (en euros) ou lifetime_budget (en euros)."
        )

    try:
        if daily_raw is not None:
            budget_eur = float(daily_raw)
        else:
            budget_eur = float(lifetime_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return error_payload("Le budget doit être un nombre (en euros).")
    if budget_eur < 1:
        return error_payload("Le budget doit être >= 1€.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.campaign import Campaign

        campaign = Campaign(campaign_id)
        if daily_raw is not None:
            campaign[Campaign.Field.daily_budget] = euros_to_cents(budget_eur)
        else:
            campaign[Campaign.Field.lifetime_budget] = euros_to_cents(budget_eur)
        campaign.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_campaign_budget")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "UPDATED_BUDGET",
        "campaign_id": campaign_id,
        "daily_budget": round(budget_eur, 2) if daily_raw is not None else None,
        "lifetime_budget": round(budget_eur, 2) if lifetime_raw is not None else None,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
