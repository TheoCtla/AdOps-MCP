"""Tool: google_ads_list_accounts.

Liste les comptes Google Ads accessibles sous le MCC configuré ; c'est le
point d'entrée naturel d'un workflow car la majorité des autres tools
attendent un ``customer_id`` de compte client.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import parse_customer_id
from google_ads.helpers import (
    enum_name,
    error_payload,
    format_google_ads_error,
)
from google_ads.queries import LIST_ACCOUNTS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_list_accounts"

_ALLOWED_STATUSES = frozenset({"ENABLED", "SUSPENDED", "CANCELED"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List Google Ads accounts accessible under the configured manager account (MCC).\n"
        "\n"
        "Use this tool whenever the user asks which Google Ads accounts are available, "
        "wants to discover a customer_id before running a report, needs to check whether a "
        "specific client is reachable, or wants to audit the MCC hierarchy. This is typically "
        "the first tool to call in any Google Ads workflow, because most other Google Ads "
        "tools require a customer_id that this tool surfaces.\n"
        "\n"
        "Returns a JSON object with two keys: `total` (int) and `accounts` (array). Each "
        "account entry contains: customer_id (string, digits only), name (descriptive name, "
        "may be empty), currency (ISO 4217 code, e.g. 'EUR'), timezone (IANA tz, e.g. "
        "'Europe/Paris'), is_manager (boolean — true for intermediate MCC nodes, false for "
        "leaf advertiser accounts), and status (one of ENABLED, SUSPENDED, CANCELED, "
        "CLOSED, UNKNOWN).\n"
        "\n"
        "By default the tool returns only ENABLED leaf accounts (is_manager=false). Set "
        "`include_managers` to true when the user asks about the MCC tree or intermediate "
        "managers. Set `status` to SUSPENDED or CANCELED to surface inactive accounts. The "
        "tool never mutates anything — it is safe to call for exploration."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "include_managers": {
                "type": "boolean",
                "description": (
                    "If true, include intermediate manager (MCC) accounts in the result. "
                    "Default: false (only leaf advertiser accounts are returned)."
                ),
                "default": False,
            },
            "status": {
                "type": "string",
                "enum": ["ENABLED", "SUSPENDED", "CANCELED"],
                "description": (
                    "Filter accounts by lifecycle status. Default: ENABLED. Use SUSPENDED "
                    "or CANCELED to audit inactive accounts."
                ),
                "default": "ENABLED",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_list_accounts.

    Retourne toujours une ``list[TextContent]`` ; en cas d'erreur, le
    contenu est un JSON ``{"error": "..."}`` exploitable par Claude pour
    expliquer le problème à l'utilisateur sans exposer de stacktrace.
    """
    args = arguments or {}
    include_managers = bool(args.get("include_managers", False))
    status = args.get("status", "ENABLED")

    if status not in _ALLOWED_STATUSES:
        return error_payload(
            f"Statut invalide : '{status}'. Valeurs acceptées : "
            + ", ".join(sorted(_ALLOWED_STATUSES))
            + "."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = LIST_ACCOUNTS_QUERY.format(status=status)

    try:
        response = ga_service.search(
            customer_id=client.login_customer_id,
            query=query,
        )
        accounts: list[dict[str, Any]] = []
        for row in response:
            cc = row.customer_client
            if not include_managers and cc.manager:
                continue
            accounts.append(
                {
                    "customer_id": parse_customer_id(cc.client_customer),
                    "name": cc.descriptive_name or "",
                    "currency": cc.currency_code or "",
                    "timezone": cc.time_zone or "",
                    "is_manager": bool(cc.manager),
                    "status": enum_name(cc.status),
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:  # défense en profondeur — on ne laisse rien remonter brut
        log.exception("Erreur inattendue dans google_ads_list_accounts")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {"total": len(accounts), "accounts": accounts}
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
