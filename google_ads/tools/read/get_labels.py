"""Tool: google_ads_get_labels.

Liste les labels définis dans le compte. Utile pour comprendre
l'organisation du compte et filtrer par label dans les rapports.
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
    error_payload,
    format_google_ads_error,
)
from google_ads.queries import LABELS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_labels"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch all labels defined in a Google Ads advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `total_labels`, and `labels` (array). "
        "Each entry contains: label_id, name, description (or null if no description is set). "
        "Labels are organizational tags applied to campaigns, ad groups, ads, or keywords — "
        "this tool lists the label definitions themselves, not their assignments. No date "
        "range, no campaign filter — labels are account-level entities.\n"
        "\n"
        "Use this tool to understand how the account is organized, check what labels exist "
        "before recommending a labeling strategy, or verify label names the user references "
        "in conversation."
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
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_labels."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
    except ValueError as ex:
        return error_payload(str(ex))

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    labels: list[dict[str, Any]] = []

    try:
        response = ga_service.search(customer_id=customer_id, query=LABELS_QUERY)
        for row in response:
            lbl = row.label
            labels.append(
                {
                    "label_id": str(lbl.id),
                    "name": lbl.name or "",
                    "description": lbl.text_label.description or None,
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_labels")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "total_labels": len(labels),
        "labels": labels,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
