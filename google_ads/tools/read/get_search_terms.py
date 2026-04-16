"""Tool: google_ads_get_search_terms.

Termes de recherche réellement tapés par les utilisateurs et qui ont
déclenché des annonces, avec le keyword qui a matché. Indispensable pour
identifier les négatifs à ajouter et les nouveaux intents à exploiter.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent, Tool

from google_ads.auth import GoogleAdsConfigError, get_google_ads_client
from google_ads.formatting import default_date_range, micros_to_euros, safe_ratio
from google_ads.helpers import (
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    numeric_id,
    round_money,
)
from google_ads.queries import SEARCH_TERMS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_search_terms"

_LIMIT_DEFAULT = 200
_LIMIT_MAX = 1000


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the actual search terms users typed that triggered ads in a Google Ads search "
        "campaign, paired with the keyword each search term matched.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters` (echo of the filters "
        "applied), `total_search_terms`, `totals` (aggregated impressions, clicks, cost in "
        "euros, conversions over the returned terms), and `search_terms` (array sorted by cost "
        "desc, capped by `limit`). Each entry contains: search_term (the raw user query), "
        "status (ADDED / EXCLUDED / ADDED_EXCLUDED / NONE / UNKNOWN — indicates whether this "
        "term has already been added as a keyword or excluded as a negative), matched_keyword "
        "(the keyword.text that triggered the ad), match_type (EXACT/PHRASE/BROAD), campaign_id, "
        "campaign_name, ad_group_id, ad_group_name, impressions, clicks, cost (euros), "
        "conversions, conversion_value, ctr, avg_cpc (euros), cpa (euros, null when no "
        "conversions).\n"
        "\n"
        "Use this tool to find wasteful search terms that should be added as negatives, "
        "discover new high-intent queries to add as keywords, audit search intent mismatch, or "
        "investigate why a campaign is spending on irrelevant clicks. `min_cost` and "
        "`only_without_conversions` are especially useful to surface spend leaks. Defaults to "
        "the last 7 full days (J-8 to J-1), all campaigns/ad groups, no filters, up to 200 "
        "terms sorted by cost."
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
                "description": "Optional numeric campaign ID to scope the query.",
            },
            "ad_group_id": {
                "type": "string",
                "description": "Optional numeric ad-group ID to scope the query.",
            },
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-8.",
            },
            "date_to": {
                "type": "string",
                "description": "End of window (YYYY-MM-DD). Default: J-1.",
            },
            "min_cost": {
                "type": "number",
                "minimum": 0,
                "description": (
                    "Minimum cost in euros for a search term to be included "
                    "(e.g. 1.0 hides terms that cost less than 1€). Useful to "
                    "focus the audit on meaningful spend."
                ),
            },
            "min_impressions": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Minimum impressions for a search term to be included. "
                    "Default: 0 (no filter)."
                ),
                "default": 0,
            },
            "only_without_conversions": {
                "type": "boolean",
                "description": (
                    "If true, return only search terms with 0 conversions — "
                    "prime candidates for negative-keyword addition. "
                    "Default: false."
                ),
                "default": False,
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": _LIMIT_MAX,
                "description": (
                    f"Maximum number of search terms returned (sorted by cost "
                    f"desc). Default: {_LIMIT_DEFAULT}. Capped at "
                    f"{_LIMIT_MAX}."
                ),
                "default": _LIMIT_DEFAULT,
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_search_terms."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    min_cost_raw = args.get("min_cost")
    if min_cost_raw is not None:
        try:
            min_cost_eur = float(min_cost_raw)
        except (TypeError, ValueError):
            return error_payload("min_cost doit être un nombre (en euros).")
        if min_cost_eur < 0:
            return error_payload("min_cost doit être >= 0.")
    else:
        min_cost_eur = None

    min_impr_raw = args.get("min_impressions", 0)
    try:
        min_impressions = int(min_impr_raw) if min_impr_raw is not None else 0
    except (TypeError, ValueError):
        return error_payload("min_impressions doit être un entier >= 0.")
    if min_impressions < 0:
        return error_payload("min_impressions doit être >= 0.")

    only_without_conv = bool(args.get("only_without_conversions", False))

    limit_raw = args.get("limit", _LIMIT_DEFAULT)
    try:
        limit = int(limit_raw) if limit_raw is not None else _LIMIT_DEFAULT
    except (TypeError, ValueError):
        return error_payload("limit doit être un entier entre 1 et 1000.")
    if limit < 1 or limit > _LIMIT_MAX:
        return error_payload(
            f"limit doit être entre 1 et {_LIMIT_MAX}."
        )

    filters: list[str] = []
    if campaign_id:
        filters.append(f"AND campaign.id = {campaign_id}")
    if ad_group_id:
        filters.append(f"AND ad_group.id = {ad_group_id}")
    if min_cost_eur is not None and min_cost_eur > 0:
        min_cost_micros = int(min_cost_eur * 1_000_000)
        filters.append(f"AND metrics.cost_micros >= {min_cost_micros}")
    if min_impressions > 0:
        filters.append(f"AND metrics.impressions >= {min_impressions}")
    extra_where = "\n      ".join(filters)

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = SEARCH_TERMS_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        extra_where=extra_where,
        limit=limit,
    )

    search_terms: list[dict[str, Any]] = []
    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            conversions = float(row.metrics.conversions or 0.0)
            if only_without_conv and conversions > 0:
                continue

            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversion_value = float(row.metrics.conversions_value or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            search_terms.append(
                {
                    "search_term": row.search_term_view.search_term or "",
                    "status": enum_name(row.search_term_view.status),
                    "matched_keyword": row.segments.keyword.info.text or "",
                    "match_type": enum_name(
                        row.segments.keyword.info.match_type
                    ),
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name or "",
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": round_money(cost_euros),
                    "conversions": round(conversions, 2),
                    "conversion_value": round_money(conversion_value),
                    "ctr": safe_ratio(clicks, impressions, decimals=4),
                    "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
                    "cpa": safe_ratio(cost_euros, conversions, decimals=2),
                }
            )

            total_impressions += impressions
            total_clicks += clicks
            total_cost_micros += cost_micros
            total_conversions += conversions
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_search_terms")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "filters": {
            "campaign_id": campaign_id or None,
            "ad_group_id": ad_group_id or None,
            "min_cost": min_cost_eur,
            "min_impressions": min_impressions,
            "only_without_conversions": only_without_conv,
            "limit": limit,
        },
        "total_search_terms": len(search_terms),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
        },
        "search_terms": search_terms,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
