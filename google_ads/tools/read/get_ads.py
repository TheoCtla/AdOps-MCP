"""Tool: google_ads_get_ads.

Récupère les annonces avec leur copy complet (headlines, descriptions,
paths, final URLs) et leurs performances. Parse les RSA et ETA ; retourne
un squelette métrique uniquement pour les autres types d'ads.
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
    ALLOWED_PERF_STATUSES,
    clean_customer_id,
    enum_name,
    error_payload,
    format_google_ads_error,
    nullable_enum,
    numeric_id,
    parse_ad_text_assets,
    round_money,
)
from google_ads.queries import ADS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_ads"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the ads (creatives) of a Google Ads account with their full copy (headlines, "
        "descriptions, paths, final URLs), ad strength, and performance metrics.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters`, `total_ads`, "
        "`totals` (aggregated impressions, clicks, cost, conversions), and `ads` (array sorted "
        "by impressions desc). Each ad entry contains: ad_id, ad_type (e.g. RESPONSIVE_SEARCH_AD, "
        "EXPANDED_TEXT_AD, CALL_ONLY_AD, ...), status, ad_strength (EXCELLENT / GOOD / AVERAGE "
        "/ POOR / NO_ADS, null for ad types that don't expose it such as ETA), campaign_id, "
        "campaign_name, ad_group_id, ad_group_name, final_urls (list), headlines (list of "
        "{text, pinned}), descriptions (list of {text, pinned}), path1, path2, impressions, "
        "clicks, cost, conversions, conversion_value, ctr, avg_cpc, cpa.\n"
        "\n"
        "For RESPONSIVE_SEARCH_AD, headlines and descriptions are parsed from the asset lists, "
        "with their pinned position (HEADLINE_1/2/3, DESCRIPTION_1/2, or null when unpinned). "
        "For EXPANDED_TEXT_AD (deprecated but still present on legacy accounts), headlines are "
        "reconstructed from headline_part1/2/3 and descriptions from description/description2; "
        "pinned is always null. For other ad types (Performance Max, Shopping, Call-Only, "
        "Video, ...), headlines and descriptions are returned as empty lists and a `note` field "
        "explains the limitation — this is expected: this tool primarily targets RSA/ETA copy.\n"
        "\n"
        "Use this tool to audit ad copy, find underperforming creatives, check ad strength and "
        "pin configuration across an ad group, review final URLs, or answer 'what are the "
        "headlines of this campaign?'. Defaults to ENABLED ads over J-8 to J-1."
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
            "status": {
                "type": "string",
                "enum": ["ENABLED", "PAUSED", "REMOVED"],
                "description": "Ad status filter. Default: ENABLED.",
                "default": "ENABLED",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_ads.

    Parse les Responsive Search Ads (RSA), les Expanded Text Ads (ETA,
    legacy), et renvoie un squelette métrique uniquement pour les autres
    types (Performance Max, Shopping, Call-Only, Video, …) avec une note
    explicative — conforme à l'objectif du tool qui cible les RSA/ETA.
    """
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    status = args.get("status") or "ENABLED"
    if status not in ALLOWED_PERF_STATUSES:
        return error_payload(
            f"Statut invalide : '{status}'. Valeurs acceptées : "
            + ", ".join(sorted(ALLOWED_PERF_STATUSES))
            + "."
        )

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    filters: list[str] = []
    if campaign_id:
        filters.append(f"AND campaign.id = {campaign_id}")
    if ad_group_id:
        filters.append(f"AND ad_group.id = {ad_group_id}")
    extra_where = "\n      ".join(filters)

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = ADS_QUERY.format(
        status=status,
        date_from=date_from,
        date_to=date_to,
        extra_where=extra_where,
    )

    ads: list[dict[str, Any]] = []
    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            cost_micros = int(row.metrics.cost_micros or 0)
            impressions = int(row.metrics.impressions or 0)
            clicks = int(row.metrics.clicks or 0)
            conversions = float(row.metrics.conversions or 0.0)
            conversion_value = float(row.metrics.conversions_value or 0.0)
            cost_euros = micros_to_euros(cost_micros) or 0.0

            ad = row.ad_group_ad.ad
            ad_type = enum_name(ad.type_)
            ad_strength = nullable_enum(row.ad_group_ad.ad_strength)

            entry: dict[str, Any] = {
                "ad_id": str(ad.id),
                "ad_type": ad_type,
                "status": enum_name(row.ad_group_ad.status),
                "ad_strength": ad_strength,
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name or "",
                "ad_group_id": str(row.ad_group.id),
                "ad_group_name": row.ad_group.name or "",
                "final_urls": list(ad.final_urls),
                "headlines": [],
                "descriptions": [],
                "path1": None,
                "path2": None,
            }

            if ad_type == "RESPONSIVE_SEARCH_AD":
                rsa = ad.responsive_search_ad
                entry["headlines"] = parse_ad_text_assets(rsa.headlines)
                entry["descriptions"] = parse_ad_text_assets(rsa.descriptions)
                entry["path1"] = rsa.path1 or None
                entry["path2"] = rsa.path2 or None
            elif ad_type == "EXPANDED_TEXT_AD":
                eta = ad.expanded_text_ad
                # ETA : on reconstruit des listes {text, pinned=None} depuis les
                # champs scalaires, en ignorant les parts vides (headline_part3
                # et description2 sont optionnels).
                eta_headlines = [
                    eta.headline_part1,
                    eta.headline_part2,
                    eta.headline_part3,
                ]
                eta_descriptions = [eta.description, eta.description2]
                entry["headlines"] = [
                    {"text": h, "pinned": None} for h in eta_headlines if h
                ]
                entry["descriptions"] = [
                    {"text": d, "pinned": None} for d in eta_descriptions if d
                ]
                entry["path1"] = eta.path1 or None
                entry["path2"] = eta.path2 or None
            else:
                entry["note"] = (
                    "Ad type not fully supported for copy extraction. "
                    "Metrics only."
                )

            entry.update(
                {
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

            ads.append(entry)

            total_impressions += impressions
            total_clicks += clicks
            total_cost_micros += cost_micros
            total_conversions += conversions
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_ads")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "filters": {
            "campaign_id": campaign_id or None,
            "ad_group_id": ad_group_id or None,
            "status": status,
        },
        "total_ads": len(ads),
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
        },
        "ads": ads,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
