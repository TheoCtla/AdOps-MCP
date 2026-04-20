"""Tool: google_ads_add_keyword.

Ajoute un mot-clé positif dans un ad group avec match type et CPC
optionnel.
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
    numeric_id,
    round_money,
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_add_keyword"

_ALLOWED_MATCH_TYPES = frozenset({"EXACT", "PHRASE", "BROAD"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Add a positive keyword to a Google Ads ad group, enabling ads to show for matching "
        "search queries.\n"
        "\n"
        "Returns a JSON confirmation with success status, keyword_text, match_type, optional "
        "cpc_bid, and the resource_name of the created keyword.\n"
        "\n"
        "Use this tool when the user identifies a new keyword opportunity (e.g. from search "
        "terms analysis) and wants to add it. Optionally set a specific CPC bid in euros; if "
        "omitted, the keyword inherits the ad group's default bid.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Adding a keyword immediately makes the ad group "
        "eligible to serve ads for matching queries and impacts live campaigns."
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
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Numeric ad group ID where the keyword will be added. Use "
                    "google_ads_get_adgroup_performance to find it."
                ),
            },
            "keyword_text": {
                "type": "string",
                "description": "The keyword text to add (e.g. 'lmnp ancien').",
            },
            "match_type": {
                "type": "string",
                "enum": ["EXACT", "PHRASE", "BROAD"],
                "description": "Match type for the keyword.",
            },
            "cpc_bid": {
                "type": "number",
                "minimum": 0.01,
                "description": (
                    "Optional max CPC bid in euros. If omitted, the keyword "
                    "inherits the ad group default bid. On smart-bidding "
                    "campaigns (Target CPA, Maximize Conversions, etc.) this "
                    "value is ignored by Google."
                ),
            },
        },
        "required": ["customer_id", "ad_group_id", "keyword_text", "match_type"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_add_keyword."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not ad_group_id:
        return error_payload("Paramètre 'ad_group_id' requis.")

    keyword_text = args.get("keyword_text")
    if not isinstance(keyword_text, str) or not keyword_text.strip():
        return error_payload("Paramètre 'keyword_text' requis (texte non vide).")
    keyword_text = keyword_text.strip()

    match_type = args.get("match_type")
    if match_type not in _ALLOWED_MATCH_TYPES:
        return error_payload(
            f"match_type invalide : '{match_type}'. "
            f"Valeurs acceptées : {', '.join(sorted(_ALLOWED_MATCH_TYPES))}."
        )

    cpc_bid_raw = args.get("cpc_bid")
    cpc_bid_eur: float | None = None
    if cpc_bid_raw is not None:
        try:
            cpc_bid_eur = float(cpc_bid_raw)
        except (TypeError, ValueError):
            return error_payload("cpc_bid doit être un nombre (en euros).")
        if cpc_bid_eur < 0.01:
            return error_payload("cpc_bid doit être >= 0.01€.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    agc_op = operation.ad_group_criterion_operation
    criterion = agc_op.create
    criterion.ad_group = ga_service.ad_group_path(customer_id, ad_group_id)
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
    criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    if cpc_bid_eur is not None:
        criterion.cpc_bid_micros = int(cpc_bid_eur * 1_000_000)

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_add_keyword")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].ad_group_criterion_result.resource_name
    )

    payload = {
        "success": True,
        "action": "ADDED_KEYWORD",
        "keyword_text": keyword_text,
        "match_type": match_type,
        "ad_group_id": ad_group_id,
        "cpc_bid": round_money(cpc_bid_eur),
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
