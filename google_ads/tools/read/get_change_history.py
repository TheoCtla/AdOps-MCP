"""Tool: google_ads_get_change_history.

Historique des modifications récentes sur le compte — qui a changé quoi,
quand et depuis quel client (UI, API, scripts, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import default_date_range
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
)
from google_ads.queries import CHANGE_HISTORY_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_change_history"

_LIMIT_DEFAULT = 50
_LIMIT_MAX = 200


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the recent change history of a Google Ads account: who modified what, when, "
        "and from which client (Google Ads UI, API, scripts, etc.).\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `total_changes`, and "
        "`changes` (array sorted by change_date_time desc). Each entry contains: "
        "change_date_time (ISO 8601), user_email, resource_type (CAMPAIGN / AD_GROUP / AD / "
        "...), resource_name (full Google Ads resource path), changed_fields (comma-separated "
        "list of modified field names), client_type (GOOGLE_ADS_WEB_CLIENT / "
        "GOOGLE_ADS_AUTOMATED_RULE / GOOGLE_ADS_SCRIPTS / ...), operation (CREATE / UPDATE / "
        "REMOVE). Does not include old/new values to keep payloads manageable.\n"
        "\n"
        "Use this tool to audit recent account changes, investigate unexpected performance "
        "shifts ('what changed yesterday?'), check who modified a campaign, or verify that "
        "automated rules are firing correctly. Defaults to J-8 to J-1, up to 50 changes."
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
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-8.",
            },
            "date_to": {
                "type": "string",
                "description": "End of window (YYYY-MM-DD). Default: J-1.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": _LIMIT_MAX,
                "description": (
                    f"Max changes returned. Default: {_LIMIT_DEFAULT}. "
                    f"Max: {_LIMIT_MAX}."
                ),
                "default": _LIMIT_DEFAULT,
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_change_history."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
    except ValueError as ex:
        return error_payload(str(ex))

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    limit_raw = args.get("limit", _LIMIT_DEFAULT)
    try:
        limit = int(limit_raw) if limit_raw is not None else _LIMIT_DEFAULT
    except (TypeError, ValueError):
        return error_payload(f"limit doit être un entier entre 1 et {_LIMIT_MAX}.")
    if limit < 1 or limit > _LIMIT_MAX:
        return error_payload(f"limit doit être entre 1 et {_LIMIT_MAX}.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = CHANGE_HISTORY_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    changes: list[dict[str, Any]] = []

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            ce = row.change_event
            changed_fields = str(ce.changed_fields) if ce.changed_fields else ""

            changes.append(
                {
                    "change_date_time": ce.change_date_time or "",
                    "user_email": ce.user_email or "",
                    "resource_type": enum_name(ce.change_resource_type),
                    "resource_name": ce.change_resource_name or "",
                    "changed_fields": changed_fields,
                    "client_type": enum_name(ce.client_type),
                    "operation": enum_name(ce.resource_change_operation),
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_change_history")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_changes": len(changes),
        "changes": changes,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
