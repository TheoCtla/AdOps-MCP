"""Tool: meta_ads_get_account_info.

Informations générales d'un compte publicitaire Meta : devise, timezone,
statut, spend cap, business name, etc.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import (
    ACCOUNT_STATUS_MAP,
    error_payload,
    format_meta_error,
    safe_float,
)


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_get_account_info"

_CORE_FIELDS = [
    "id", "name", "account_status", "currency",
    "timezone_name", "amount_spent", "balance",
    "spend_cap", "business_name", "created_time",
]

_OPTIONAL_FIELDS = [
    "owner", "funding_source_details",
    "disable_reason", "min_campaign_group_spend_cap",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch general information about a Meta Ads account: status, currency, timezone, "
        "lifetime spend, balance, spend cap, business name, and creation date.\n"
        "\n"
        "Returns a JSON object with account details. Fields that require elevated permissions "
        "(owner, funding_source_details) may be null if inaccessible.\n"
        "\n"
        "Use this tool to verify account configuration, check the currency and timezone "
        "before interpreting metrics, audit the spend cap, or understand account status. "
        "No date range — this returns account-level settings."
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
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_get_account_info."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id or not isinstance(ad_account_id, str):
        return error_payload(
            "Paramètre 'ad_account_id' requis (format 'act_XXXXX')."
        )

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        try:
            info = account.api_get(fields=_CORE_FIELDS + _OPTIONAL_FIELDS)
        except Exception:
            info = account.api_get(fields=_CORE_FIELDS)

        raw_status = int(info.get("account_status", 0))

        payload = {
            "account_id": info.get("id", ""),
            "name": info.get("name", ""),
            "status": ACCOUNT_STATUS_MAP.get(raw_status, f"UNKNOWN({raw_status})"),
            "currency": info.get("currency", ""),
            "timezone": info.get("timezone_name", ""),
            "lifetime_spend": str(safe_float(info.get("amount_spent"))),
            "balance": str(safe_float(info.get("balance"))) if info.get("balance") else None,
            "spend_cap": str(safe_float(info.get("spend_cap"))) if info.get("spend_cap") else None,
            "business_name": info.get("business_name") or None,
            "created_time": info.get("created_time") or None,
            "disable_reason": info.get("disable_reason") or None,
        }
    except Exception as ex:
        log.exception("Erreur dans meta_ads_get_account_info")
        return error_payload(format_meta_error(ex))

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
