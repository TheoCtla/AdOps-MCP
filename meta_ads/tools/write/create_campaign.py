"""Tool: meta_ads_create_campaign.

Crée une nouvelle campagne Meta Ads. Toujours en PAUSED par défaut pour
review avant activation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, euros_to_cents, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_create_campaign"

_ALLOWED_OBJECTIVES = frozenset({
    "OUTCOME_LEADS", "OUTCOME_TRAFFIC", "OUTCOME_SALES",
    "OUTCOME_AWARENESS", "OUTCOME_ENGAGEMENT", "OUTCOME_APP_PROMOTION",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a new Meta Ads campaign on an ad account. The campaign is created in PAUSED "
        "status by default for review before activation.\n"
        "\n"
        "Returns a JSON confirmation with the new campaign_id, name, objective, and status.\n"
        "\n"
        "Use this tool when the user wants to set up a new campaign. Available objectives: "
        "OUTCOME_LEADS, OUTCOME_TRAFFIC, OUTCOME_SALES, OUTCOME_AWARENESS, "
        "OUTCOME_ENGAGEMENT, OUTCOME_APP_PROMOTION. Budget can be set at campaign level "
        "(daily or lifetime) or left to the ad set level.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new campaign is created on the ad account."
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
            "name": {
                "type": "string",
                "description": "Campaign name.",
            },
            "objective": {
                "type": "string",
                "enum": list(_ALLOWED_OBJECTIVES),
                "description": "Campaign objective.",
            },
            "daily_budget": {
                "type": "number",
                "minimum": 1,
                "description": (
                    "Optional daily budget in euros. Converted to centimes. "
                    "Omit to set budget at ad set level."
                ),
            },
            "lifetime_budget": {
                "type": "number",
                "minimum": 1,
                "description": (
                    "Optional lifetime budget in euros. Converted to centimes. "
                    "Cannot be combined with daily_budget."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["PAUSED", "ACTIVE"],
                "description": "Initial status. Default: PAUSED.",
                "default": "PAUSED",
            },
            "special_ad_categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Special ad categories if applicable: CREDIT, EMPLOYMENT, "
                    "HOUSING, SOCIAL_ISSUES_ELECTIONS_POLITICS. Empty array if none."
                ),
            },
        },
        "required": ["ad_account_id", "name", "objective"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_create_campaign."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    name = args.get("name")
    objective = args.get("objective")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not name or not isinstance(name, str):
        return error_payload("Paramètre 'name' requis (texte non vide).")
    if objective not in _ALLOWED_OBJECTIVES:
        return error_payload(
            f"objective invalide : '{objective}'. "
            f"Valeurs : {', '.join(sorted(_ALLOWED_OBJECTIVES))}."
        )

    daily_raw = args.get("daily_budget")
    lifetime_raw = args.get("lifetime_budget")
    if daily_raw is not None and lifetime_raw is not None:
        return error_payload(
            "Fournir daily_budget OU lifetime_budget, pas les deux."
        )

    status = args.get("status") or "PAUSED"
    special_cats = args.get("special_ad_categories") or []

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.adobjects.campaign import Campaign

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            Campaign.Field.name: name,
            Campaign.Field.objective: objective,
            Campaign.Field.status: status,
            Campaign.Field.special_ad_categories: special_cats,
            "buying_type": "AUCTION",
        }
        if daily_raw is not None:
            params[Campaign.Field.daily_budget] = euros_to_cents(float(daily_raw))
        elif lifetime_raw is not None:
            params[Campaign.Field.lifetime_budget] = euros_to_cents(float(lifetime_raw))
        else:
            # Pas de budget campagne → budget géré au niveau ad set.
            params["is_adset_budget_sharing_enabled"] = False

        campaign = account.create_campaign(params=params)
    except Exception as ex:
        log.exception("Erreur dans meta_ads_create_campaign")
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "CREATED_CAMPAIGN",
        "campaign_id": campaign.get("id", ""),
        "name": name,
        "objective": objective,
        "status": status,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
