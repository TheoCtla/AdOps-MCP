"""Tool: google_ads_get_negative_keywords.

Liste les mots-clés négatifs existants (niveau campagne et niveau ad
group). Pas de période — ce sont des settings, pas des métriques.
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
    numeric_id,
)
from google_ads.queries import (
    NEGATIVE_KEYWORDS_ADGROUP_QUERY,
    NEGATIVE_KEYWORDS_CAMPAIGN_QUERY,
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_negative_keywords"

_ALLOWED_LEVELS = frozenset({"campaign", "adgroup", "all"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "List existing negative keywords (both campaign-level and ad-group-level) on a Google "
        "Ads advertiser account. Negative keywords are settings, not metrics — no date range "
        "is involved.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `filters` (echo), `total_negatives`, "
        "`campaign_level` (array of campaign-level negatives), and `adgroup_level` (array of "
        "ad-group-level negatives). Campaign-level entries contain: criterion_id, keyword_text, "
        "match_type (EXACT/PHRASE/BROAD), campaign_id, campaign_name. Ad-group-level entries "
        "additionally contain ad_group_id and ad_group_name. When `level` is 'campaign' or "
        "'adgroup', the other list is returned as an empty array for a predictable schema.\n"
        "\n"
        "Use this tool to audit the existing negative-keyword coverage before adding new "
        "negatives (to avoid duplicates and conflicts), to review the negative strategy of a "
        "specific campaign, or to explain why a given search term is not generating clicks. "
        "Pair with google_ads_get_search_terms to identify gaps in negative-keyword coverage."
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
            "campaign_id": {
                "type": "string",
                "description": (
                    "Optional numeric campaign ID to scope the query. Filters "
                    "both campaign-level negatives of this campaign AND the "
                    "ad-group-level negatives attached to its ad groups."
                ),
            },
            "level": {
                "type": "string",
                "enum": ["campaign", "adgroup", "all"],
                "description": (
                    "Which level of negatives to return. 'campaign' = only "
                    "campaign-level, 'adgroup' = only ad-group-level, 'all' = "
                    "both. Default: 'all'."
                ),
                "default": "all",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_negative_keywords."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    level = (args.get("level") or "all").lower()
    if level not in _ALLOWED_LEVELS:
        return error_payload(
            f"level invalide : '{level}'. Valeurs acceptées : "
            + ", ".join(sorted(_ALLOWED_LEVELS))
            + "."
        )

    extra_where = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    campaign_level: list[dict[str, Any]] = []
    adgroup_level: list[dict[str, Any]] = []

    try:
        if level in ("campaign", "all"):
            query = NEGATIVE_KEYWORDS_CAMPAIGN_QUERY.format(extra_where=extra_where)
            response = ga_service.search(customer_id=customer_id, query=query)
            for row in response:
                campaign_level.append(
                    {
                        "criterion_id": str(row.campaign_criterion.criterion_id),
                        "keyword_text": row.campaign_criterion.keyword.text or "",
                        "match_type": enum_name(
                            row.campaign_criterion.keyword.match_type
                        ),
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name or "",
                    }
                )

        if level in ("adgroup", "all"):
            query = NEGATIVE_KEYWORDS_ADGROUP_QUERY.format(extra_where=extra_where)
            response = ga_service.search(customer_id=customer_id, query=query)
            for row in response:
                adgroup_level.append(
                    {
                        "criterion_id": str(row.ad_group_criterion.criterion_id),
                        "keyword_text": row.ad_group_criterion.keyword.text or "",
                        "match_type": enum_name(
                            row.ad_group_criterion.keyword.match_type
                        ),
                        "ad_group_id": str(row.ad_group.id),
                        "ad_group_name": row.ad_group.name or "",
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name or "",
                    }
                )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_negative_keywords")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "filters": {
            "campaign_id": campaign_id or None,
            "level": level,
        },
        "total_negatives": len(campaign_level) + len(adgroup_level),
        "campaign_level": campaign_level,
        "adgroup_level": adgroup_level,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
