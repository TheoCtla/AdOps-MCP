"""Tool: google_ads_add_negative_keyword.

Ajoute un mot-clé négatif au niveau campagne ou ad group. Tool le plus
demandé pour stopper rapidement le gaspillage identifié via les search
terms.
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
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_add_negative_keyword"

_ALLOWED_MATCH_TYPES = frozenset({"EXACT", "PHRASE", "BROAD"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Add a negative keyword to a Google Ads campaign or ad group, preventing ads from "
        "showing for that search term.\n"
        "\n"
        "Returns a JSON confirmation with success status, the level (campaign or ad_group), "
        "keyword_text, match_type, and the resource_name of the newly created negative.\n"
        "\n"
        "Use this tool after identifying wasteful search terms with "
        "google_ads_get_search_terms. Check google_ads_get_negative_keywords first to ensure "
        "the negative doesn't already exist. Pass ad_group_id to scope the negative to a "
        "single ad group; omit it to apply at campaign level (blocks the term across all ad "
        "groups).\n"
        "\n"
        "⚠️ This tool MODIFIES data. Adding a negative keyword immediately prevents ads "
        "from showing for matching searches and impacts live campaigns."
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
            "keyword_text": {
                "type": "string",
                "description": (
                    "The negative keyword text to add (e.g. 'définition', "
                    "'gratuit', 'formation')."
                ),
            },
            "match_type": {
                "type": "string",
                "enum": ["EXACT", "PHRASE", "BROAD"],
                "description": (
                    "Match type for the negative. EXACT blocks only that exact "
                    "query. PHRASE blocks queries containing the phrase. BROAD "
                    "blocks queries containing all words in any order."
                ),
            },
            "campaign_id": {
                "type": "string",
                "description": "Numeric campaign ID where the negative will be added.",
            },
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Optional numeric ad group ID. If provided, the negative is "
                    "scoped to this ad group only (not the whole campaign)."
                ),
            },
        },
        "required": ["customer_id", "keyword_text", "match_type", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_add_negative_keyword."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

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

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    if ad_group_id:
        agc_op = operation.ad_group_criterion_operation
        criterion = agc_op.create
        criterion.ad_group = ga_service.ad_group_path(customer_id, ad_group_id)
        criterion.negative = True
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
        level = "ad_group"
    else:
        cc_op = operation.campaign_criterion_operation
        criterion = cc_op.create
        criterion.campaign = ga_service.campaign_path(customer_id, campaign_id)
        criterion.negative = True
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
        level = "campaign"

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_add_negative_keyword")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resp = response.mutate_operation_responses[0]
    if ad_group_id:
        resource_name = resp.ad_group_criterion_result.resource_name
    else:
        resource_name = resp.campaign_criterion_result.resource_name

    payload = {
        "success": True,
        "action": "ADDED_NEGATIVE",
        "level": level,
        "keyword_text": keyword_text,
        "match_type": match_type,
        "campaign_id": campaign_id,
        "ad_group_id": ad_group_id or None,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
