"""Tool: meta_ads_create_adset.

Crée un nouvel ad set dans une campagne Meta existante. Toujours en
PAUSED par défaut.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, euros_to_cents, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_create_adset"

_ALLOWED_GOALS = frozenset({
    "LEAD_GENERATION", "LINK_CLICKS", "IMPRESSIONS", "REACH",
    "CONVERSIONS", "LANDING_PAGE_VIEWS", "OFFSITE_CONVERSIONS",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a new ad set in an existing Meta Ads campaign. The ad set is created in "
        "PAUSED status by default.\n"
        "\n"
        "Returns a JSON confirmation with the new adset_id, name, and status.\n"
        "\n"
        "Use this tool to set up a new ad set with targeting, budget, and optimization goal. "
        "The targeting parameter must be a JSON object with at minimum geo_locations. "
        "Common optimization goals: LEAD_GENERATION, LINK_CLICKS, IMPRESSIONS, REACH, "
        "CONVERSIONS, LANDING_PAGE_VIEWS, OFFSITE_CONVERSIONS.\n"
        "\n"
        "For outcome-based campaigns (e.g. OUTCOME_LEADS), Meta requires a promoted_object "
        "linking the ad set to a concrete asset — typically {\"page_id\": \"<FB_PAGE_ID>\"} "
        "for lead ads. Pass it via the promoted_object parameter.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new ad set is created in the campaign."
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
                "description": "Campaign ID to create the ad set in.",
            },
            "name": {
                "type": "string",
                "description": "Ad set name.",
            },
            "optimization_goal": {
                "type": "string",
                "enum": list(_ALLOWED_GOALS),
                "description": "What Meta optimizes delivery for.",
            },
            "targeting": {
                "type": "object",
                "description": (
                    "Targeting spec. At minimum: "
                    "{\"geo_locations\": {\"countries\": [\"FR\"]}, "
                    "\"age_min\": 18, \"age_max\": 65}."
                ),
            },
            "daily_budget": {
                "type": "number",
                "minimum": 1,
                "description": "Optional daily budget in euros.",
            },
            "lifetime_budget": {
                "type": "number",
                "minimum": 1,
                "description": "Optional lifetime budget in euros.",
            },
            "billing_event": {
                "type": "string",
                "description": "Billing event. Default: IMPRESSIONS.",
                "default": "IMPRESSIONS",
            },
            "bid_strategy": {
                "type": "string",
                "enum": [
                    "LOWEST_COST_WITHOUT_CAP",
                    "LOWEST_COST_WITH_BID_CAP",
                    "COST_CAP",
                ],
                "description": (
                    "Bid strategy. Default: LOWEST_COST_WITHOUT_CAP."
                ),
                "default": "LOWEST_COST_WITHOUT_CAP",
            },
            "bid_amount": {
                "type": "number",
                "minimum": 0.01,
                "description": (
                    "Bid amount in euros. Required when bid_strategy is "
                    "LOWEST_COST_WITH_BID_CAP or COST_CAP."
                ),
            },
            "start_time": {
                "type": "string",
                "description": "Optional start time (ISO 8601).",
            },
            "end_time": {
                "type": "string",
                "description": "Optional end time (ISO 8601). Required for lifetime budget.",
            },
            "promoted_object": {
                "type": "object",
                "description": (
                    "Asset promoted by this ad set. Required by Meta for "
                    "outcome-based campaigns (OUTCOME_LEADS, etc.). "
                    "Example for lead ads: {\"page_id\": \"<FB_PAGE_ID>\"}. "
                    "Other common shapes: {\"pixel_id\": \"...\", "
                    "\"custom_event_type\": \"PURCHASE\"}, "
                    "{\"application_id\": \"...\", \"object_store_url\": \"...\"}."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["PAUSED", "ACTIVE"],
                "description": "Initial status. Default: PAUSED.",
                "default": "PAUSED",
            },
        },
        "required": ["ad_account_id", "campaign_id", "name", "optimization_goal", "targeting"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_create_adset."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    campaign_id = args.get("campaign_id")
    name = args.get("name")
    optimization_goal = args.get("optimization_goal")
    targeting = args.get("targeting")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")
    if not name:
        return error_payload("Paramètre 'name' requis.")
    if optimization_goal not in _ALLOWED_GOALS:
        return error_payload(
            f"optimization_goal invalide : '{optimization_goal}'. "
            f"Valeurs : {', '.join(sorted(_ALLOWED_GOALS))}."
        )
    if not targeting or not isinstance(targeting, dict):
        return error_payload("Paramètre 'targeting' requis (objet JSON).")

    # Advantage Audience requis par Meta — désactivé par défaut.
    if "targeting_automation" not in targeting:
        targeting["targeting_automation"] = {"advantage_audience": 0}

    daily_raw = args.get("daily_budget")
    lifetime_raw = args.get("lifetime_budget")
    if daily_raw is not None and lifetime_raw is not None:
        return error_payload(
            "Fournir daily_budget OU lifetime_budget, pas les deux."
        )

    status = args.get("status") or "PAUSED"
    billing_event = args.get("billing_event") or "IMPRESSIONS"
    bid_strategy = args.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"

    bid_amount_raw = args.get("bid_amount")
    if bid_strategy in ("LOWEST_COST_WITH_BID_CAP", "COST_CAP") and bid_amount_raw is None:
        return error_payload(
            f"bid_amount requis quand bid_strategy = '{bid_strategy}'."
        )

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.adobjects.adset import AdSet

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            AdSet.Field.name: name,
            AdSet.Field.campaign_id: campaign_id,
            AdSet.Field.optimization_goal: optimization_goal,
            AdSet.Field.billing_event: billing_event,
            AdSet.Field.targeting: targeting,
            AdSet.Field.status: status,
            AdSet.Field.bid_strategy: bid_strategy,
        }
        if bid_amount_raw is not None:
            params[AdSet.Field.bid_amount] = euros_to_cents(float(bid_amount_raw))
        if daily_raw is not None:
            params[AdSet.Field.daily_budget] = euros_to_cents(float(daily_raw))
        if lifetime_raw is not None:
            params[AdSet.Field.lifetime_budget] = euros_to_cents(float(lifetime_raw))

        start_time = args.get("start_time")
        end_time = args.get("end_time")
        if start_time:
            params[AdSet.Field.start_time] = start_time
        if end_time:
            params[AdSet.Field.end_time] = end_time

        promoted_object = args.get("promoted_object")
        if promoted_object:
            params[AdSet.Field.promoted_object] = promoted_object

        adset = account.create_ad_set(params=params)
    except Exception as ex:
        log.exception("Erreur dans meta_ads_create_adset")
        from facebook_business.exceptions import FacebookRequestError

        if isinstance(ex, FacebookRequestError):
            error_detail = {
                "error": True,
                "api_error_code": ex.api_error_code(),
                "api_error_message": ex.api_error_message(),
                "api_error_type": ex.api_error_type(),
                "body": str(ex.body()),
                "http_status": ex.http_status(),
            }
            return [TextContent(
                type="text",
                text=json.dumps(error_detail, ensure_ascii=False),
            )]
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "CREATED_ADSET",
        "adset_id": adset.get("id", ""),
        "name": name,
        "campaign_id": campaign_id,
        "status": status,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
