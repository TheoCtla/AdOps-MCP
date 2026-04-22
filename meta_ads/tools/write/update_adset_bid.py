"""Tool: meta_ads_update_adset_bid.

Modifie la stratégie d'enchère d'un ad set Meta.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, euros_to_cents, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_update_adset_bid"

_ALLOWED_STRATEGIES = frozenset({
    "LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Update the bid strategy of a Meta Ads ad set.\n"
        "\n"
        "Returns a JSON confirmation with the new bid strategy and amount.\n"
        "\n"
        "Use this tool to change how Meta bids in auctions — e.g. switch to cost cap, set "
        "a bid cap, or revert to lowest cost. bid_amount (in euros) is required when "
        "bid_strategy is LOWEST_COST_WITH_BID_CAP or COST_CAP.\n"
        "\n"
        "⚠️ This tool MODIFIES data. The bid change takes effect immediately and impacts "
        "ad delivery and costs."
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
            "adset_id": {
                "type": "string",
                "description": "Numeric ad set ID to update.",
            },
            "bid_strategy": {
                "type": "string",
                "enum": list(_ALLOWED_STRATEGIES),
                "description": "New bid strategy.",
            },
            "bid_amount": {
                "type": "number",
                "minimum": 0.01,
                "description": (
                    "Bid amount in euros. Required for "
                    "LOWEST_COST_WITH_BID_CAP and COST_CAP."
                ),
            },
        },
        "required": ["ad_account_id", "adset_id", "bid_strategy"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_update_adset_bid."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")
    bid_strategy = args.get("bid_strategy")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")
    if bid_strategy not in _ALLOWED_STRATEGIES:
        return error_payload(
            f"bid_strategy invalide : '{bid_strategy}'. "
            f"Valeurs : {', '.join(sorted(_ALLOWED_STRATEGIES))}."
        )

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
        from facebook_business.adobjects.adset import AdSet

        adset = AdSet(adset_id)
        adset[AdSet.Field.bid_strategy] = bid_strategy
        if bid_amount_raw is not None:
            adset[AdSet.Field.bid_amount] = euros_to_cents(float(bid_amount_raw))
        adset.remote_update()
    except Exception as ex:
        log.exception("Erreur dans meta_ads_update_adset_bid")
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
            return [TextContent(type="text", text=json.dumps(error_detail, ensure_ascii=False))]
        return error_payload(format_meta_error(ex))

    bid_eur = round(float(bid_amount_raw), 2) if bid_amount_raw is not None else None

    payload = {
        "success": True,
        "action": "UPDATED_BID",
        "adset_id": adset_id,
        "bid_strategy": bid_strategy,
        "bid_amount": bid_eur,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
