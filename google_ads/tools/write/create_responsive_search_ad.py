"""Tool: google_ads_create_responsive_search_ad.

Crée une RSA (Responsive Search Ad) dans un ad group. Format d'annonce
standard Google Ads Search : 3-15 headlines, 2-4 descriptions, pins
optionnels.
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

TOOL_NAME = "google_ads_create_responsive_search_ad"

_HEADLINE_MIN = 3
_HEADLINE_MAX = 15
_HEADLINE_CHAR_MAX = 30
_DESC_MIN = 2
_DESC_MAX = 4
_DESC_CHAR_MAX = 90
_PATH_CHAR_MAX = 15


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a new Responsive Search Ad (RSA) in a Google Ads ad group with headlines, "
        "descriptions, final URL, optional display paths, and optional pins.\n"
        "\n"
        "Returns a JSON confirmation with the resource_name of the created ad. The ad is "
        "created in PAUSED status by default for review before activation — use "
        "google_ads_enable_ad to go live.\n"
        "\n"
        "Use this tool when the user wants to create a new search ad. Constraints: 3-15 "
        "headlines (max 30 chars each), 2-4 descriptions (max 90 chars each), path1/path2 "
        "(max 15 chars each). Pinning is optional — use pinned_headlines/pinned_descriptions "
        "to lock a specific headline/description to a position.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new ad is created in the ad group. It is PAUSED by "
        "default but can be set to ENABLED to go live immediately."
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
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Numeric ad group ID. Use "
                    "google_ads_get_adgroup_performance to find it."
                ),
            },
            "headlines": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": _HEADLINE_MIN,
                "maxItems": _HEADLINE_MAX,
                "description": (
                    f"List of headline texts ({_HEADLINE_MIN}-{_HEADLINE_MAX}, "
                    f"max {_HEADLINE_CHAR_MAX} chars each)."
                ),
            },
            "descriptions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": _DESC_MIN,
                "maxItems": _DESC_MAX,
                "description": (
                    f"List of description texts ({_DESC_MIN}-{_DESC_MAX}, "
                    f"max {_DESC_CHAR_MAX} chars each)."
                ),
            },
            "final_url": {
                "type": "string",
                "description": "Landing page URL (must start with http:// or https://).",
            },
            "path1": {
                "type": "string",
                "description": (
                    f"Optional display path part 1 (max {_PATH_CHAR_MAX} chars, "
                    f"e.g. 'medecine')."
                ),
            },
            "path2": {
                "type": "string",
                "description": (
                    f"Optional display path part 2 (max {_PATH_CHAR_MAX} chars, "
                    f"e.g. 'nice')."
                ),
            },
            "pinned_headlines": {
                "type": "object",
                "description": (
                    "Optional pins: {\"HEADLINE_1\": \"exact text\", "
                    "\"HEADLINE_2\": \"exact text\", \"HEADLINE_3\": \"exact text\"}. "
                    "The text must match one of the headlines exactly."
                ),
            },
            "pinned_descriptions": {
                "type": "object",
                "description": (
                    "Optional pins: {\"DESCRIPTION_1\": \"exact text\", "
                    "\"DESCRIPTION_2\": \"exact text\"}."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["ENABLED", "PAUSED"],
                "description": "Initial status. Default: PAUSED (review before activation).",
                "default": "PAUSED",
            },
        },
        "required": ["customer_id", "ad_group_id", "headlines", "descriptions", "final_url"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_create_responsive_search_ad."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not ad_group_id:
        return error_payload("Paramètre 'ad_group_id' requis.")

    # --- Validate headlines ---
    headlines = args.get("headlines")
    if not isinstance(headlines, list) or not (_HEADLINE_MIN <= len(headlines) <= _HEADLINE_MAX):
        return error_payload(
            f"'headlines' requis : {_HEADLINE_MIN}-{_HEADLINE_MAX} éléments."
        )
    for i, h in enumerate(headlines):
        if not isinstance(h, str) or not h.strip():
            return error_payload(f"headlines[{i}] doit être un texte non vide.")
        if len(h) > _HEADLINE_CHAR_MAX:
            return error_payload(
                f"headlines[{i}] trop long ({len(h)} chars, max {_HEADLINE_CHAR_MAX}) : \"{h}\""
            )

    # --- Validate descriptions ---
    descriptions = args.get("descriptions")
    if not isinstance(descriptions, list) or not (_DESC_MIN <= len(descriptions) <= _DESC_MAX):
        return error_payload(
            f"'descriptions' requis : {_DESC_MIN}-{_DESC_MAX} éléments."
        )
    for i, d in enumerate(descriptions):
        if not isinstance(d, str) or not d.strip():
            return error_payload(f"descriptions[{i}] doit être un texte non vide.")
        if len(d) > _DESC_CHAR_MAX:
            return error_payload(
                f"descriptions[{i}] trop long ({len(d)} chars, max {_DESC_CHAR_MAX})."
            )

    # --- Validate final_url ---
    final_url = args.get("final_url", "")
    if not isinstance(final_url, str) or not final_url.startswith(("http://", "https://")):
        return error_payload("final_url doit commencer par http:// ou https://.")

    # --- Validate paths ---
    path1 = args.get("path1") or ""
    path2 = args.get("path2") or ""
    if path1 and len(path1) > _PATH_CHAR_MAX:
        return error_payload(f"path1 trop long ({len(path1)} chars, max {_PATH_CHAR_MAX}).")
    if path2 and len(path2) > _PATH_CHAR_MAX:
        return error_payload(f"path2 trop long ({len(path2)} chars, max {_PATH_CHAR_MAX}).")

    pinned_headlines = args.get("pinned_headlines") or {}
    pinned_descriptions = args.get("pinned_descriptions") or {}
    status = args.get("status") or "PAUSED"
    if status not in ("ENABLED", "PAUSED"):
        return error_payload("status doit être ENABLED ou PAUSED.")

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")
    operation = client.get_type("MutateOperation")

    ad_group_ad_op = operation.ad_group_ad_operation
    ad_group_ad = ad_group_ad_op.create
    ad_group_ad.ad_group = ga_service.ad_group_path(customer_id, ad_group_id)
    ad_group_ad.status = client.enums.AdGroupAdStatusEnum[status]

    ad = ad_group_ad.ad
    ad.final_urls.append(final_url)

    # Build headlines with optional pins.
    for h_text in headlines:
        headline = client.get_type("AdTextAsset")
        headline.text = h_text
        for pin_pos, pin_text in pinned_headlines.items():
            if pin_text == h_text:
                headline.pinned_field = client.enums.ServedAssetFieldTypeEnum[pin_pos]
                break
        ad.responsive_search_ad.headlines.append(headline)

    # Build descriptions with optional pins.
    for d_text in descriptions:
        desc = client.get_type("AdTextAsset")
        desc.text = d_text
        for pin_pos, pin_text in pinned_descriptions.items():
            if pin_text == d_text:
                desc.pinned_field = client.enums.ServedAssetFieldTypeEnum[pin_pos]
                break
        ad.responsive_search_ad.descriptions.append(desc)

    if path1:
        ad.responsive_search_ad.path1 = path1
    if path2:
        ad.responsive_search_ad.path2 = path2

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_create_responsive_search_ad")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    resource_name = (
        response.mutate_operation_responses[0].ad_group_ad_result.resource_name
    )

    payload = {
        "success": True,
        "action": "CREATED_RSA",
        "ad_group_id": ad_group_id,
        "headlines_count": len(headlines),
        "descriptions_count": len(descriptions),
        "final_url": final_url,
        "status": status,
        "resource_name": resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
