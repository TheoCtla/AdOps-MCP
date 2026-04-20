"""Tool: google_ads_get_extensions.

Récupère les assets/extensions (sitelinks, callouts, structured snippets,
images, prix, appels) d'un compte ou d'une campagne. Pas de métriques —
ce sont des settings.
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
from google_ads.queries import CAMPAIGN_EXTENSIONS_QUERY, EXTENSIONS_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_get_extensions"

_ALLOWED_ASSET_TYPES = frozenset({
    "SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "IMAGE", "PRICE", "CALL", "ALL",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Fetch ad extensions (assets) configured on a Google Ads account or a specific "
        "campaign: sitelinks, callouts, structured snippets, images, price extensions, and "
        "call extensions.\n"
        "\n"
        "Returns a JSON object with `customer_id`, `filters`, `total_assets`, and `assets` "
        "(array). Each asset entry contains: asset_id, type (SITELINK / CALLOUT / "
        "STRUCTURED_SNIPPET / IMAGE / PRICE / CALL), name, plus type-specific fields — "
        "sitelinks include link_text, description1, description2, final_urls; callouts include "
        "callout_text; structured snippets include header and values (list); images include "
        "image_url; price extensions include price_offerings (raw object). No date range — "
        "extensions are settings, not metrics.\n"
        "\n"
        "Use this tool to audit which extensions are in place, check for missing sitelinks or "
        "callouts, review the structured snippet headers, or verify image assets before "
        "launching a campaign. Pass `campaign_id` to see only extensions linked to a specific "
        "campaign. Filter by `asset_type` to focus on one kind of extension."
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
                    "Optional numeric campaign ID. If provided, returns only "
                    "extensions linked to this campaign via campaign_asset."
                ),
            },
            "asset_type": {
                "type": "string",
                "enum": [
                    "SITELINK", "CALLOUT", "STRUCTURED_SNIPPET",
                    "IMAGE", "PRICE", "CALL", "ALL",
                ],
                "description": (
                    "Filter by extension type. Default: ALL (returns all types)."
                ),
                "default": "ALL",
            },
        },
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)


def _parse_asset(row: Any, include_campaign: bool = False) -> dict[str, Any]:
    """Parse un row GAQL asset en dict selon son type."""
    asset = row.asset
    asset_type = enum_name(asset.type_)

    entry: dict[str, Any] = {
        "asset_id": str(asset.id),
        "type": asset_type,
        "name": asset.name or "",
    }

    if asset_type == "SITELINK":
        sl = asset.sitelink_asset
        entry["link_text"] = sl.link_text or ""
        entry["description1"] = sl.description1 or ""
        entry["description2"] = sl.description2 or ""
        entry["final_urls"] = list(asset.final_urls)
    elif asset_type == "CALLOUT":
        entry["callout_text"] = asset.callout_asset.callout_text or ""
    elif asset_type == "STRUCTURED_SNIPPET":
        ss = asset.structured_snippet_asset
        entry["header"] = ss.header or ""
        entry["values"] = list(ss.values)
    elif asset_type == "IMAGE":
        entry["image_url"] = asset.image_asset.full_size.url or None
    elif asset_type == "PRICE":
        offerings = asset.price_asset.price_offerings
        entry["price_offerings"] = [str(o) for o in offerings] if offerings else []
    # CALL: no extra fields beyond id/type/name

    if include_campaign:
        entry["campaign_id"] = str(row.campaign.id)
        entry["campaign_name"] = row.campaign.name or ""

    return entry


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_get_extensions."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        campaign_id = numeric_id(args.get("campaign_id"), "campaign_id")
    except ValueError as ex:
        return error_payload(str(ex))

    asset_type = (args.get("asset_type") or "ALL").upper()
    if asset_type not in _ALLOWED_ASSET_TYPES:
        return error_payload(
            f"asset_type invalide : '{asset_type}'. Valeurs acceptées : "
            + ", ".join(sorted(_ALLOWED_ASSET_TYPES))
            + "."
        )

    extra_where = ""
    if asset_type != "ALL":
        extra_where = f"AND asset.type = '{asset_type}'"

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    if campaign_id:
        query = CAMPAIGN_EXTENSIONS_QUERY.format(
            campaign_id=campaign_id, extra_where=extra_where,
        )
    else:
        query = EXTENSIONS_QUERY.format(extra_where=extra_where)

    assets: list[dict[str, Any]] = []

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            assets.append(_parse_asset(row, include_campaign=bool(campaign_id)))
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_get_extensions")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    payload = {
        "customer_id": customer_id,
        "filters": {
            "campaign_id": campaign_id or None,
            "asset_type": asset_type,
        },
        "total_assets": len(assets),
        "assets": assets,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
