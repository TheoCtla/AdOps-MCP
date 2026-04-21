"""Tool: google_ads_update_ad_schedule.

Remplace le calendrier de diffusion d'une campagne. Supprime les
schedules existants puis crée les nouveaux en un seul appel mutate
pour garantir l'atomicité.
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
from google_ads.queries import EXISTING_AD_SCHEDULES_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_update_ad_schedule"

_ALLOWED_DAYS = frozenset({
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
    "FRIDAY", "SATURDAY", "SUNDAY",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Replace the ad schedule (dayparting) of a Google Ads campaign. This REPLACES all "
        "existing schedules — it is not incremental. Pass an empty array to remove all "
        "schedules (campaign runs 24/7).\n"
        "\n"
        "Returns a JSON confirmation with the number of removed and created schedules, plus "
        "the new schedule list.\n"
        "\n"
        "Use this tool to set or change when ads are shown (e.g. weekdays 8-22, weekends "
        "9-18). Use google_ads_get_ad_schedule to view the current schedule before modifying. "
        "Each schedule entry needs day_of_week (MONDAY-SUNDAY), start_hour (0-23), end_hour "
        "(1-24), and an optional bid_modifier (1.0 = neutral).\n"
        "\n"
        "⚠️ This tool MODIFIES data. All existing ad schedules are deleted and replaced. "
        "The change takes effect immediately and impacts live campaigns."
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
                    "Numeric campaign ID. Use "
                    "google_ads_get_campaign_performance to find it."
                ),
            },
            "schedules": {
                "type": "array",
                "description": (
                    "List of schedule slots. Empty array = remove all (24/7). "
                    "Each entry: {day_of_week, start_hour, end_hour, bid_modifier?}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "day_of_week": {
                            "type": "string",
                            "enum": [
                                "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                                "FRIDAY", "SATURDAY", "SUNDAY",
                            ],
                        },
                        "start_hour": {"type": "integer", "minimum": 0, "maximum": 23},
                        "end_hour": {"type": "integer", "minimum": 1, "maximum": 24},
                        "bid_modifier": {"type": "number", "minimum": 0},
                    },
                    "required": ["day_of_week", "start_hour", "end_hour"],
                },
            },
        },
        "required": ["customer_id", "campaign_id", "schedules"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_update_ad_schedule."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

    schedules_raw = args.get("schedules")
    if schedules_raw is None:
        return error_payload("Paramètre 'schedules' requis (tableau, peut être vide).")
    if not isinstance(schedules_raw, list):
        return error_payload("'schedules' doit être un tableau.")

    # Validate each schedule entry.
    for i, s in enumerate(schedules_raw):
        if not isinstance(s, dict):
            return error_payload(f"schedules[{i}] doit être un objet.")
        day = s.get("day_of_week")
        if day not in _ALLOWED_DAYS:
            return error_payload(
                f"schedules[{i}].day_of_week invalide : '{day}'."
            )
        sh = s.get("start_hour")
        eh = s.get("end_hour")
        if not isinstance(sh, int) or not (0 <= sh <= 23):
            return error_payload(f"schedules[{i}].start_hour doit être entre 0 et 23.")
        if not isinstance(eh, int) or not (1 <= eh <= 24):
            return error_payload(f"schedules[{i}].end_hour doit être entre 1 et 24.")
        if eh <= sh:
            return error_payload(
                f"schedules[{i}] : end_hour ({eh}) doit être > start_hour ({sh})."
            )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    # Step 1: find existing ad_schedule criteria to remove.
    query = EXISTING_AD_SCHEDULES_QUERY.format(campaign_id=campaign_id)
    operations: list[Any] = []

    try:
        lookup_resp = ga_service.search(customer_id=customer_id, query=query)
        removed_count = 0
        for row in lookup_resp:
            cid = row.campaign_criterion.criterion_id
            op = client.get_type("MutateOperation")
            op.campaign_criterion_operation.remove = (
                ga_service.campaign_criterion_path(customer_id, campaign_id, str(cid))
            )
            operations.append(op)
            removed_count += 1
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))

    # Step 2: create new schedule criteria.
    for s in schedules_raw:
        op = client.get_type("MutateOperation")
        cc_op = op.campaign_criterion_operation
        criterion = cc_op.create
        criterion.campaign = ga_service.campaign_path(customer_id, campaign_id)
        criterion.type_ = client.enums.CriterionTypeEnum.AD_SCHEDULE
        criterion.ad_schedule.day_of_week = client.enums.DayOfWeekEnum[s["day_of_week"]]
        criterion.ad_schedule.start_hour = s["start_hour"]
        criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.ad_schedule.end_hour = s["end_hour"]
        criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
        bid_mod = s.get("bid_modifier")
        if bid_mod is not None:
            criterion.bid_modifier = float(bid_mod)
        operations.append(op)

    # Step 3: execute all removes + creates atomically.
    try:
        if operations:
            ga_service.mutate(
                customer_id=customer_id,
                mutate_operations=operations,
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_update_ad_schedule")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "success": True,
        "action": "UPDATED_AD_SCHEDULE",
        "campaign_id": campaign_id,
        "removed_schedules": removed_count,
        "created_schedules": len(schedules_raw),
        "schedules": [
            {
                "day_of_week": s["day_of_week"],
                "start_hour": s["start_hour"],
                "end_hour": s["end_hour"],
                "bid_modifier": s.get("bid_modifier"),
            }
            for s in schedules_raw
        ],
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
