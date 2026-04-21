"""Tool: google_ads_update_campaign_targeting.

Ajoute ou retire des ciblages géographiques et/ou linguistiques sur une
campagne. Pour les suppressions, le tool lookup le criterion_id
correspondant avant de remove.
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
from google_ads.queries import (
    LANGUAGE_CRITERION_LOOKUP_QUERY,
    LOCATION_CRITERION_LOOKUP_QUERY,
)


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_update_campaign_targeting"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Add or remove geographic and/or language targeting on a Google Ads campaign.\n"
        "\n"
        "Returns a JSON confirmation listing which locations and languages were added or "
        "removed.\n"
        "\n"
        "Use this tool to expand or narrow a campaign's targeting — e.g. add Belgium (2056) "
        "to a France-only campaign, remove a city, or add a new language. Common geo IDs: "
        "France=2250, Belgium=2056, Switzerland=2756, Canada=2124, USA=2840, Paris=1006094. "
        "Common language IDs: French=1002, English=1000, German=1001. Use "
        "google_ads_get_campaign_settings to see current targeting. At least one of the four "
        "array parameters must be provided.\n"
        "\n"
        "⚠️ This tool MODIFIES data. Targeting changes take effect immediately and impact "
        "live campaigns."
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
            "locations_to_add": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Geo criterion IDs to add as positive location targets "
                    "(e.g. ['2250'] for France, ['1006094'] for Paris)."
                ),
            },
            "locations_to_remove": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Geo criterion IDs to remove from targeting.",
            },
            "languages_to_add": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Language criterion IDs to add "
                    "(e.g. ['1002'] for French, ['1000'] for English)."
                ),
            },
            "languages_to_remove": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Language criterion IDs to remove.",
            },
        },
        "required": ["customer_id", "campaign_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_update_campaign_targeting."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not campaign_id:
        return error_payload("Paramètre 'campaign_id' requis.")

    locs_add = args.get("locations_to_add") or []
    locs_remove = args.get("locations_to_remove") or []
    langs_add = args.get("languages_to_add") or []
    langs_remove = args.get("languages_to_remove") or []

    if not locs_add and not locs_remove and not langs_add and not langs_remove:
        return error_payload(
            "Au moins un paramètre de ciblage requis (locations_to_add, "
            "locations_to_remove, languages_to_add, languages_to_remove)."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operations: list[Any] = []

    try:
        # Add locations.
        for geo_id in locs_add:
            op = client.get_type("MutateOperation")
            criterion = op.campaign_criterion_operation.create
            criterion.campaign = ga_service.campaign_path(customer_id, campaign_id)
            criterion.location.geo_target_constant = f"geoTargetConstants/{geo_id}"
            operations.append(op)

        # Remove locations (lookup criterion_id first).
        for geo_id in locs_remove:
            query = LOCATION_CRITERION_LOOKUP_QUERY.format(
                campaign_id=campaign_id, geo_id=geo_id,
            )
            resp = ga_service.search(customer_id=customer_id, query=query)
            rows = list(resp)
            if not rows:
                return error_payload(
                    f"Location geoTargetConstants/{geo_id} non trouvée sur "
                    f"la campagne {campaign_id}."
                )
            cid = rows[0].campaign_criterion.criterion_id
            op = client.get_type("MutateOperation")
            op.campaign_criterion_operation.remove = (
                ga_service.campaign_criterion_path(customer_id, campaign_id, str(cid))
            )
            operations.append(op)

        # Add languages.
        for lang_id in langs_add:
            op = client.get_type("MutateOperation")
            criterion = op.campaign_criterion_operation.create
            criterion.campaign = ga_service.campaign_path(customer_id, campaign_id)
            criterion.language.language_constant = f"languageConstants/{lang_id}"
            operations.append(op)

        # Remove languages (lookup criterion_id first).
        for lang_id in langs_remove:
            query = LANGUAGE_CRITERION_LOOKUP_QUERY.format(
                campaign_id=campaign_id, language_id=lang_id,
            )
            resp = ga_service.search(customer_id=customer_id, query=query)
            rows = list(resp)
            if not rows:
                return error_payload(
                    f"Language languageConstants/{lang_id} non trouvée sur "
                    f"la campagne {campaign_id}."
                )
            cid = rows[0].campaign_criterion.criterion_id
            op = client.get_type("MutateOperation")
            op.campaign_criterion_operation.remove = (
                ga_service.campaign_criterion_path(customer_id, campaign_id, str(cid))
            )
            operations.append(op)

        # Execute all operations atomically.
        if operations:
            ga_service.mutate(
                customer_id=customer_id,
                mutate_operations=operations,
            )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_update_campaign_targeting")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "success": True,
        "action": "UPDATED_TARGETING",
        "campaign_id": campaign_id,
        "locations_added": locs_add,
        "locations_removed": locs_remove,
        "languages_added": langs_add,
        "languages_removed": langs_remove,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
