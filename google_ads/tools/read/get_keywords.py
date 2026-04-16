"""Tool: google_ads_get_keywords.

Audit des mots-clés : performance et signaux de qualité (Quality Score et
ses sous-scores). Utilisé pour détecter les keywords à faible QS qui
gonflent le CPC, ou pour sortir les top keywords en conversion.
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
    nullable_enum,
    numeric_id,
    round_money,
)
from google_ads.queries import KEYWORDS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_keywords"

_ALLOWED_KEYWORD_STATUSES = frozenset({"ENABLED", "PAUSED"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch keyword-level performance and quality signals for a Google Ads search account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `total_keywords`, `totals` "
        "(aggregated impressions, clicks, cost, conversions), and `keywords` (array sorted by "
        "cost desc). Each entry contains: criterion_id, keyword_text, match_type (EXACT/PHRASE/"
        "BROAD), status, quality_score (1-10, null when not computed — needs ~3 impressions/"
        "week over the last 90 days), landing_page_experience (post_click_quality_score: "
        "ABOVE_AVERAGE/AVERAGE/BELOW_AVERAGE, null when unknown), ad_relevance "
        "(creative_quality_score), expected_ctr (search_predicted_ctr), ad_group_id, "
        "ad_group_name, campaign_id, campaign_name, impressions, clicks, cost (euros), "
        "conversions, ctr, avg_cpc (euros), cpa (euros).\n"
        "\n"
        "Use this tool to audit keyword quality (especially Quality Score), find low-QS "
        "keywords that inflate CPC, check which keywords drive conversions, or scope a review "
        "to one campaign or ad group. `min_quality_score` and `min_impressions` are handy to "
        "filter out long-tail noise. Defaults to ENABLED keywords over J-8 to J-1."
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
            "min_quality_score": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": (
                    "If set, return only keywords whose quality_score is >= this "
                    "threshold. Useful to exclude low-QS noise, or invert by reading "
                    "`quality_score` in the output. Keywords with no QS (null) are "
                    "never returned when this filter is set."
                ),
            },
            "min_impressions": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Return only keywords with at least this many impressions over "
                    "the period. Default: 0 (no filter)."
                ),
                "default": 0,
            },
            "status": {
                "type": "string",
                "enum": ["ENABLED", "PAUSED"],
                "description": "Keyword status filter. Default: ENABLED.",
                "default": "ENABLED",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_keywords."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    status = args.get("status") or "ENABLED"
    if status not in _ALLOWED_KEYWORD_STATUSES:
        return error_payload(
            f"Statut invalide : '{status}'. Valeurs acceptées : "
            + ", ".join(sorted(_ALLOWED_KEYWORD_STATUSES))
            + "."
        )

    min_qs = args.get("min_quality_score")
    if min_qs is not None and (not isinstance(min_qs, int) or not 1 <= min_qs <= 10):
        return error_payload(
            "min_quality_score doit être un entier entre 1 et 10."
        )

    min_impr_raw = args.get("min_impressions", 0)
    try:
        min_impressions = int(min_impr_raw) if min_impr_raw is not None else 0
    except (TypeError, ValueError):
        return error_payload("min_impressions doit être un entier >= 0.")
    if min_impressions < 0:
        return error_payload("min_impressions doit être >= 0.")

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    extra_filters: list[str] = []
    if campaign_id:
        extra_filters.append(f"AND campaign.id = {campaign_id}")
    if ad_group_id:
        extra_filters.append(f"AND ad_group.id = {ad_group_id}")
    if min_impressions > 0:
        extra_filters.append(f"AND metrics.impressions >= {min_impressions}")
    # GAQL n'a pas de filtre direct sur quality_score : le seuil min_qs est
    # appliqué côté Python après récupération (voir plus bas).
    extra_where = "\n      ".join(extra_filters)

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = KEYWORDS_QUERY.format(
        date_from=date_from,
        date_to=date_to,
        status=status,
        extra_where=extra_where,
    )

    keywords: list[dict[str, Any]] = []
    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            qi = row.ad_group_criterion.quality_info
            qs_raw = int(qi.quality_score or 0)
            quality_score = qs_raw if 1 <= qs_raw <= 10 else None

            if min_qs is not None:
                if quality_score is None or quality_score < min_qs:
                    continue

            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversions = float(row.metrics.conversions or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            keywords.append(
                {
                    "criterion_id": str(row.ad_group_criterion.criterion_id),
                    "keyword_text": row.ad_group_criterion.keyword.text or "",
                    "match_type": enum_name(
                        row.ad_group_criterion.keyword.match_type
                    ),
                    "status": enum_name(row.ad_group_criterion.status),
                    "quality_score": quality_score,
                    "landing_page_experience": nullable_enum(
                        qi.post_click_quality_score
                    ),
                    "ad_relevance": nullable_enum(qi.creative_quality_score),
                    "expected_ctr": nullable_enum(qi.search_predicted_ctr),
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name or "",
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": round_money(cost_euros),
                    "conversions": round(conversions, 2),
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
        log.exception("Erreur inattendue dans google_ads_get_keywords")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "total_keywords": len(keywords),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
        },
        "keywords": keywords,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
