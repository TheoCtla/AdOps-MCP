"""Tool: google_ads_get_age_gender_performance.

Performance par tranche d'âge et/ou genre. Exécute 1 ou 2 queries GAQL
(age_range_view et gender_view) selon le paramètre ``breakdown``.
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
from google_ads.queries import AGE_PERFORMANCE_QUERY, GENDER_PERFORMANCE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_age_gender_performance"

_ALLOWED_BREAKDOWNS = frozenset({"AGE", "GENDER", "BOTH"})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch performance metrics segmented by age range and/or gender for a Google Ads "
        "advertiser account.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `date_range`, `filters`, `totals`, and "
        "either `age_breakdown`, `gender_breakdown`, or both depending on the `breakdown` "
        "parameter. Age entries contain: age_range (AGE_RANGE_18_24 / AGE_RANGE_25_34 / "
        "AGE_RANGE_35_44 / AGE_RANGE_45_54 / AGE_RANGE_55_64 / AGE_RANGE_65_UP / "
        "AGE_RANGE_UNDETERMINED), ad_group_id, ad_group_name, campaign_id, campaign_name, "
        "impressions, clicks, cost (euros), conversions, conversion_value, ctr, avg_cpc, cpa. "
        "Gender entries contain: gender (MALE / FEMALE / UNDETERMINED), same metrics.\n"
        "\n"
        "Use this tool to identify demographic segments that convert well or poorly, inform "
        "bid adjustments by age/gender, or understand audience composition. Defaults to BOTH "
        "breakdowns over J-8 to J-1."
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
            "date_from": {
                "type": "string",
                "description": "Start of window (YYYY-MM-DD). Default: J-8.",
            },
            "date_to": {
                "type": "string",
                "description": "End of window (YYYY-MM-DD). Default: J-1.",
            },
            "breakdown": {
                "type": "string",
                "enum": ["AGE", "GENDER", "BOTH"],
                "description": (
                    "Which demographic dimension(s) to return. AGE = age_breakdown "
                    "only, GENDER = gender_breakdown only, BOTH = both. "
                    "Default: BOTH."
                ),
                "default": "BOTH",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


def _parse_rows(
    response: Any,
    dimension_key: str,
    dimension_accessor: Any,
) -> tuple[list[dict[str, Any]], int, int, int, float, float]:
    """Parse les rows d'une query age/gender et retourne (entries, totals accumulés)."""
    entries: list[dict[str, Any]] = []
    t_impr = 0
    t_clicks = 0
    t_cost_micros = 0
    t_conv = 0.0
    t_conv_val = 0.0

    for row in response:
        cost_micros = int(row.metrics.cost_micros or 0)
        impressions = int(row.metrics.impressions or 0)
        clicks = int(row.metrics.clicks or 0)
        conversions = float(row.metrics.conversions or 0.0)
        conversion_value = float(row.metrics.conversions_value or 0.0)
        cost_euros = micros_to_euros(cost_micros) or 0.0

        entry: dict[str, Any] = {
            dimension_key: enum_name(dimension_accessor(row)),
            "ad_group_id": str(row.ad_group.id),
            "ad_group_name": row.ad_group.name or "",
            "campaign_id": str(row.campaign.id),
            "campaign_name": row.campaign.name or "",
            "impressions": impressions,
            "clicks": clicks,
            "cost": round_money(cost_euros),
            "conversions": round(conversions, 2),
            "conversion_value": round_money(conversion_value),
            "ctr": safe_ratio(clicks, impressions, decimals=4),
            "avg_cpc": safe_ratio(cost_euros, clicks, decimals=2),
            "cpa": safe_ratio(cost_euros, conversions, decimals=2),
        }
        entries.append(entry)

        t_impr += impressions
        t_clicks += clicks
        t_cost_micros += cost_micros
        t_conv += conversions
        t_conv_val += conversion_value

    return entries, t_impr, t_clicks, t_cost_micros, t_conv, t_conv_val


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_age_gender_performance."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    breakdown = (args.get("breakdown") or "BOTH").upper()
    if breakdown not in _ALLOWED_BREAKDOWNS:
        return error_payload(
            f"breakdown invalide : '{breakdown}'. Valeurs acceptées : "
            + ", ".join(sorted(_ALLOWED_BREAKDOWNS))
            + "."
        )

    default_from, default_to = default_date_range(days_back=7)
    date_from = args.get("date_from") or default_from
    date_to = args.get("date_to") or default_to

    extra_where = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    total_impressions = 0
    total_clicks = 0
    total_cost_micros = 0
    total_conversions = 0.0
    total_conversion_value = 0.0

    age_breakdown: list[dict[str, Any]] | None = None
    gender_breakdown: list[dict[str, Any]] | None = None

    try:
        if breakdown in ("AGE", "BOTH"):
            query = AGE_PERFORMANCE_QUERY.format(
                date_from=date_from, date_to=date_to, extra_where=extra_where,
            )
            response = ga_service.search(customer_id=customer_id, query=query)
            age_breakdown, ai, ac, acm, aco, acv = _parse_rows(
                response,
                "age_range",
                lambda r: r.ad_group_criterion.age_range.type_,
            )
            total_impressions += ai
            total_clicks += ac
            total_cost_micros += acm
            total_conversions += aco
            total_conversion_value += acv

        if breakdown in ("GENDER", "BOTH"):
            query = GENDER_PERFORMANCE_QUERY.format(
                date_from=date_from, date_to=date_to, extra_where=extra_where,
            )
            response = ga_service.search(customer_id=customer_id, query=query)
            gender_breakdown, gi, gc, gcm, gco, gcv = _parse_rows(
                response,
                "gender",
                lambda r: r.ad_group_criterion.gender.type_,
            )
            total_impressions += gi
            total_clicks += gc
            total_cost_micros += gcm
            total_conversions += gco
            total_conversion_value += gcv
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_age_gender_performance")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload: dict[str, Any] = {
        "customer_id": customer_id,
        "date_range": {"from": date_from, "to": date_to},
        "filters": {
            "breakdown": breakdown,
            "campaign_id": campaign_id or None,
        },
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round_money(micros_to_euros(total_cost_micros)) or 0.0,
            "conversions": round(total_conversions, 2),
            "conversion_value": round_money(total_conversion_value),
        },
    }
    if age_breakdown is not None:
        payload["age_breakdown"] = age_breakdown
    if gender_breakdown is not None:
        payload["gender_breakdown"] = gender_breakdown

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
