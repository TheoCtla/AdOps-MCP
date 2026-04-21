"""Tool: meta_ads_list_ad_accounts.

Liste tous les comptes publicitaires accessibles via le Business Manager
Meta — comptes possédés (owned) et comptes clients (accès délégué).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import ACCOUNT_STATUS_MAP, error_payload, format_meta_error, safe_float


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_list_ad_accounts"

_ACCOUNT_STATUS_MAP = ACCOUNT_STATUS_MAP

_STATUS_FILTER_MAP = {
    "ACTIVE": 1,
    "CLOSED": 101,
    "UNSETTLED": 3,
}

_ACCOUNT_FIELDS = [
    "id", "name", "account_status", "currency",
    "timezone_name", "amount_spent",
]


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List all Meta Ads (Facebook/Instagram) ad accounts accessible under the configured "
        "Business Manager.\n"
        "\n"
        "Returns a JSON object with `total`, `owned_accounts` (accounts owned by the Business "
        "Manager), and `client_accounts` (accounts with delegated access from third parties). "
        "Each account entry contains: account_id (format 'act_XXXXX' — use this ID for all "
        "other Meta tools), name, status (ACTIVE / DISABLED / CLOSED / ...), currency (ISO "
        "4217), timezone, lifetime_spend (total spend in account currency).\n"
        "\n"
        "Use this tool as the entry point for any Meta Ads workflow — most other Meta tools "
        "require an account_id that this tool surfaces. Filter by status to see only active "
        "accounts (default) or audit closed/unsettled ones."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ACTIVE", "CLOSED", "UNSETTLED", "ALL"],
                "description": (
                    "Filter accounts by status. Default: ACTIVE. Use ALL to "
                    "see every account regardless of status."
                ),
                "default": "ACTIVE",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "description": (
                    "Max accounts to return (across owned + client). "
                    "Default: 100. Increase if the BM has many accounts."
                ),
                "default": 100,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
)


def _parse_account(account: Any) -> dict[str, Any]:
    """Parse un objet AdAccount Meta en dict."""
    raw_status = int(account.get("account_status", 0))
    return {
        "account_id": account.get("id", ""),
        "name": account.get("name", ""),
        "status": _ACCOUNT_STATUS_MAP.get(raw_status, f"UNKNOWN({raw_status})"),
        "currency": account.get("currency", ""),
        "timezone": account.get("timezone_name", ""),
        "lifetime_spend": str(safe_float(account.get("amount_spent"))),
    }


def _matches_status(account: Any, status_code: int | None) -> bool:
    """Filtre un compte par status code (None = pas de filtre)."""
    if status_code is None:
        return True
    return int(account.get("account_status", 0)) == status_code


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_list_ad_accounts."""
    args = arguments or {}
    status = args.get("status", "ACTIVE")

    if status not in ("ACTIVE", "CLOSED", "UNSETTLED", "ALL"):
        return error_payload(
            f"Statut invalide : '{status}'. "
            "Valeurs acceptées : ACTIVE, CLOSED, UNSETTLED, ALL."
        )

    limit_raw = args.get("limit", 100)
    try:
        limit = int(limit_raw) if limit_raw is not None else 100
    except (TypeError, ValueError):
        return error_payload("limit doit être un entier entre 1 et 500.")
    if limit < 1 or limit > 500:
        return error_payload("limit doit être entre 1 et 500.")

    status_code = _STATUS_FILTER_MAP.get(status)  # None if "ALL"

    try:
        business_id = get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    try:
        from facebook_business.adobjects.business import Business

        business = Business(business_id)
        remaining = limit
        truncated = False

        # Owned accounts — iterate lazily, stop when limit reached.
        owned_accounts: list[dict[str, Any]] = []
        owned_cursor = business.get_owned_ad_accounts(
            fields=_ACCOUNT_FIELDS, params={"limit": remaining},
        )
        for account in owned_cursor:
            if _matches_status(account, status_code):
                owned_accounts.append(_parse_account(account))
                if len(owned_accounts) >= remaining:
                    truncated = True
                    break

        # Client accounts — use remaining budget.
        remaining = limit - len(owned_accounts)
        client_accounts: list[dict[str, Any]] = []
        if remaining > 0:
            client_cursor = business.get_client_ad_accounts(
                fields=_ACCOUNT_FIELDS, params={"limit": remaining},
            )
            for account in client_cursor:
                if _matches_status(account, status_code):
                    client_accounts.append(_parse_account(account))
                    if len(client_accounts) >= remaining:
                        truncated = True
                        break
    except Exception as ex:
        log.exception("Erreur dans meta_ads_list_ad_accounts")
        return error_payload(format_meta_error(ex))

    payload = {
        "total": len(owned_accounts) + len(client_accounts),
        "owned_accounts": owned_accounts,
        "client_accounts": client_accounts,
        "truncated": truncated,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
