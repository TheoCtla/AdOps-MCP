"""Tool: google_ads_get_ad_schedule.

Calendrier de diffusion (ad schedule) configuré sur une campagne : jours,
heures de début/fin, ajustements d'enchères horaires.
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
from google_ads.queries import AD_SCHEDULE_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_ad_schedule"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch the ad schedule (dayparting) configured on a specific Google Ads campaign: "
        "which days/hours ads are shown and the bid modifier for each slot.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `campaign_id`, `campaign_name`, "
        "`total_schedules`, and `schedules` (array). Each entry contains: day_of_week "
        "(MONDAY-SUNDAY), start_hour (0-23), start_minute (ZERO / FIFTEEN / THIRTY / "
        "FORTY_FIVE), end_hour (0-24), end_minute, bid_modifier (1.0 = neutral, >1 = boost, "
        "<1 = reduce, null if not set). If total_schedules is 0, the campaign runs 24/7 with "
        "no dayparting configured. No date range — this returns settings.\n"
        "\n"
        "Use this tool to verify when ads are scheduled to run, check bid adjustments by "
        "time-of-day, audit dayparting configuration before modifying it, or explain why a "
        "campaign doesn't serve during certain hours. Pair with "
        "google_ads_get_hour_of_day_performance to compare the schedule against actual "
        "performance data."
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
                    "Numeric campaign ID to inspect. Use "
                    "google_ads_get_campaign_performance to find it."
                ),
            },
        },
        "required": ["customer_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_ad_schedule."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload(
            "Paramètre 'campaign_id' requis. Utilise "
            "google_ads_get_campaign_performance pour le trouver."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    query = AD_SCHEDULE_QUERY.format(campaign_id=campaign_id)

    schedules: list[dict[str, Any]] = []
    campaign_name = ""

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            sched = row.campaign_criterion.ad_schedule
            bid_mod = row.campaign_criterion.bid_modifier
            campaign_name = row.campaign.name or ""

            schedules.append(
                {
                    "day_of_week": enum_name(sched.day_of_week),
                    "start_hour": int(sched.start_hour),
                    "start_minute": enum_name(sched.start_minute),
                    "end_hour": int(sched.end_hour),
                    "end_minute": enum_name(sched.end_minute),
                    "bid_modifier": round(bid_mod, 2) if bid_mod else None,
                }
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_ad_schedule")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "total_schedules": len(schedules),
        "schedules": schedules,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
