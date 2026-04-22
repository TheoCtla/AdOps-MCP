"""Tool: meta_ads_create_ad.

Crée une nouvelle publicité dans un ad set Meta existant. Toujours en
PAUSED par défaut.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_create_ad"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a new ad in an existing Meta Ads ad set. The ad is created in PAUSED status "
        "by default. Provide either a creative_id (existing creative) or a creative_spec "
        "(inline creative definition).\n"
        "\n"
        "Returns a JSON confirmation with the new ad_id, name, and status.\n"
        "\n"
        "Use this tool to add a new ad to an ad set. For creative_spec, provide an object "
        "with at minimum: body (primary text), title (headline), image_hash or image_url, "
        "object_url (destination), and call_to_action_type (LEARN_MORE, SHOP_NOW, etc.).\n"
        "\n"
        "⚠️ This tool MODIFIES data. A new ad is created in the ad set."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "ad_account_id": {
                "type": "string",
                "description": (
                    "Meta ad account ID (format 'act_XXXXX'). "
                    "Use meta_ads_list_ad_accounts to find it."
                ),
            },
            "adset_id": {
                "type": "string",
                "description": "Ad set ID to create the ad in.",
            },
            "name": {
                "type": "string",
                "description": "Ad name.",
            },
            "creative_id": {
                "type": "string",
                "description": (
                    "ID of an existing creative to use. Provide this OR "
                    "creative_spec, not both."
                ),
            },
            "creative_spec": {
                "type": "object",
                "description": (
                    "Inline creative spec: {body, title, link_description, "
                    "image_hash, call_to_action_type, object_url}."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["PAUSED", "ACTIVE"],
                "description": "Initial status. Default: PAUSED.",
                "default": "PAUSED",
            },
        },
        "required": ["ad_account_id", "adset_id", "name"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_create_ad."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    adset_id = args.get("adset_id")
    name = args.get("name")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not adset_id:
        return error_payload("Paramètre 'adset_id' requis.")
    if not name:
        return error_payload("Paramètre 'name' requis.")

    creative_id = args.get("creative_id")
    creative_spec = args.get("creative_spec")

    if creative_id and creative_spec:
        return error_payload(
            "Fournir creative_id OU creative_spec, pas les deux."
        )
    if not creative_id and not creative_spec:
        return error_payload(
            "Fournir creative_id (creative existant) ou creative_spec (inline)."
        )

    status = args.get("status") or "PAUSED"

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    page_id: str | None = None
    instagram_actor_id: str | None = None

    try:
        from facebook_business.adobjects.ad import Ad
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(ad_account_id)

        params: dict[str, Any] = {
            Ad.Field.name: name,
            Ad.Field.adset_id: adset_id,
            Ad.Field.status: status,
        }

        if creative_id:
            params[Ad.Field.creative] = {"creative_id": creative_id}
        else:
            # Transform flat creative_spec into object_story_spec format.
            body = creative_spec.get("body", "")
            title = creative_spec.get("title", "")
            link_description = creative_spec.get("link_description", "")
            image_hash = creative_spec.get("image_hash")
            cta_type = creative_spec.get("call_to_action_type", "LEARN_MORE")
            object_url = creative_spec.get("object_url", "")

            # 1. Auto-détection page_id
            page_id = creative_spec.get("page_id")
            instagram_actor_id = creative_spec.get("instagram_actor_id")

            if not page_id:
                # Méthode prioritaire : regarder les ads existantes du compte.
                try:
                    existing_ads = account.get_ads(
                        fields=["creative{object_story_spec}"],
                        params={"limit": 5},
                    )
                    for existing_ad in existing_ads:
                        creative_data = existing_ad.get("creative", {})
                        oss = creative_data.get("object_story_spec", {})
                        if oss.get("page_id"):
                            page_id = oss["page_id"]
                            if (
                                not instagram_actor_id
                                and oss.get("instagram_actor_id")
                            ):
                                instagram_actor_id = oss[
                                    "instagram_actor_id"
                                ]
                            break
                except Exception:
                    log.exception(
                        "Erreur lors de l'auto-détection de page_id "
                        "via les ads existantes"
                    )

            if not page_id:
                # Fallback : chercher dans les client_pages du BM.
                try:
                    from facebook_business.adobjects.business import (
                        Business,
                    )

                    business_id = get_meta_api()
                    business = Business(business_id)
                    client_pages = business.get_client_pages(
                        fields=["id", "name"]
                    )
                    # Prendre la première page trouvée — pas idéal mais
                    # mieux que rien. En prod, l'utilisateur devrait
                    # passer page_id.
                    for cp in client_pages:
                        page_id = cp["id"]
                        break
                except Exception:
                    log.exception(
                        "Erreur lors du fallback page_id via client_pages"
                    )

            if not page_id:
                return error_payload(
                    "Impossible de trouver la page Facebook pour ce compte. "
                    "Ajoutez page_id dans creative_spec. "
                    "Astuce : regardez les ads existantes du compte dans "
                    "Meta Ads Manager."
                )

            link_data: dict[str, Any] = {
                "message": body,
                "name": title,
                "description": link_description,
                "link": object_url,
                "call_to_action": {
                    "type": cta_type,
                    "value": {"link": object_url},
                },
            }
            if image_hash:
                link_data["image_hash"] = image_hash

            story_spec: dict[str, Any] = {
                "page_id": page_id,
                "link_data": link_data,
            }
            if instagram_actor_id:
                story_spec["instagram_actor_id"] = instagram_actor_id

            params[Ad.Field.creative] = {"object_story_spec": story_spec}

        ad = account.create_ad(params=params)
    except Exception as ex:
        log.exception("Erreur dans meta_ads_create_ad")
        from facebook_business.exceptions import FacebookRequestError

        if isinstance(ex, FacebookRequestError):
            error_detail = {
                "error": True,
                "api_error_code": ex.api_error_code(),
                "api_error_message": ex.api_error_message(),
                "api_error_type": ex.api_error_type(),
                "body": str(ex.body()),
                "http_status": ex.http_status(),
            }
            return [TextContent(
                type="text",
                text=json.dumps(error_detail, ensure_ascii=False),
            )]
        return error_payload(format_meta_error(ex))

    payload = {
        "success": True,
        "action": "CREATED_AD",
        "ad_id": ad.get("id", ""),
        "name": name,
        "adset_id": adset_id,
        "status": status,
        "page_id": page_id,
        "instagram_actor_id": instagram_actor_id,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
