"""Tool: google_ads_get_conversion_actions.

Liste les actions de conversion configurées dans le compte. Indispensable
pour comprendre ce que mesurent les métriques "conversions" dans tous
les autres tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
)
from google_ads.queries import CONVERSION_ACTIONS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_conversion_actions"

_ALLOWED_STATUSES = frozenset({"ENABLED", "REMOVED", "HIDDEN"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the conversion actions configured in a Google Ads advertiser account: what "
        "events are tracked as conversions, how they are counted, and which attribution model "
        "is used.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `filters`, `total_conversion_actions`, and "
        "`conversion_actions` (array). Each entry contains: conversion_id, name, type "
        "(WEBPAGE / CLICK_TO_CALL / STORE_VISIT / IMPORT / ...), status, category "
        "(SUBMIT_LEAD_FORM / PURCHASE / SIGNUP / ...), counting_type (ONE_PER_CLICK / "
        "MANY_PER_CLICK), attribution_model (e.g. GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN). "
        "No date range — these are account settings.\n"
        "\n"
        "Use this tool to understand what 'conversions' means across all other tools, audit "
        "the conversion setup (are all important events tracked?), check the counting type "
        "(one vs many per click), or investigate attribution model choices. This is often the "
        "first thing to review when a client's conversion data looks unexpected."
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
            "status": {
                "type": "string",
                "enum": ["ENABLED", "REMOVED", "HIDDEN"],
                "description": (
                    "Filter conversion actions by status. Default: ENABLED. "
                    "Use REMOVED or HIDDEN to audit inactive actions."
                ),
                "default": "ENABLED",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_conversion_actions."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
    except ValueError as ex:
        return error_payload(str(ex))

    status = args.get("status") or "ENABLED"
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
    query = CONVERSION_ACTIONS_QUERY.format(status=status)

    actions: list[dict[str, Any]] = []

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            ca = row.conversion_action
            actions.append(
                {
                    "conversion_id": str(ca.id),
                    "name": ca.name or "",
                    "type": enum_name(ca.type_),
                    "status": enum_name(ca.status),
                    "category": enum_name(ca.category),
                    "counting_type": enum_name(ca.counting_type),
                    "attribution_model": enum_name(
                        ca.attribution_model_settings.attribution_model
                    ),
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_conversion_actions")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "filters": {"status": status},
        "total_conversion_actions": len(actions),
        "conversion_actions": actions,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
