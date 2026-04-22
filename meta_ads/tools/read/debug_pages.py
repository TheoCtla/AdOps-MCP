"""Tool: meta_ads_debug_pages.

Tool temporaire de debug pour lister les pages Facebook accessibles
via différentes méthodes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_debug_pages"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Debug tool: list Facebook pages accessible for a Meta Ads account via multiple "
        "methods (promote_pages and business owned_pages). Temporary — used to identify "
        "the correct page_id for ad creation."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "ad_account_id": {
                "type": "string",
                "description": "Meta ad account ID (format 'act_XXXXX').",
            },
        },
        "required": ["ad_account_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_debug_pages."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    from facebook_business.adobjects.adaccount import AdAccount

    results: dict[str, Any] = {}
    account = AdAccount(ad_account_id)

    # Méthode 1 : promote_pages
    try:
        pages = list(account.get_promote_pages(fields=["id", "name"]))
        results["method1_promote_pages"] = [
            {"id": p["id"], "name": p.get("name")} for p in pages
        ]
    except Exception as ex:
        results["method1_error"] = str(ex)

    # Méthode 2 : pages du BM
    try:
        from facebook_business.adobjects.business import Business

        business_id = get_meta_api()
        business = Business(business_id)
        pages2 = list(business.get_owned_pages(fields=["id", "name"]))
        results["method2_business_pages"] = [
            {"id": p["id"], "name": p.get("name")} for p in pages2
        ]
    except Exception as ex:
        results["method2_error"] = str(ex)

    # Méthode 3 : client_pages du BM
    try:
        from facebook_business.adobjects.business import Business

        business_id = get_meta_api()
        business = Business(business_id)
        pages3 = list(business.get_client_pages(fields=["id", "name"]))
        results["method3_client_pages"] = [
            {"id": p["id"], "name": p.get("name")} for p in pages3
        ]
    except Exception as ex:
        results["method3_error"] = str(ex)

    # Méthode 4 : regarder les ads existantes du compte
    # pour trouver quelle page elles utilisent
    try:
        ads = account.get_ads(
            fields=["creative{object_story_spec}"],
            params={"limit": 5},
        )
        pages_from_ads = []
        for ad in ads:
            creative = ad.get("creative", {})
            oss = creative.get("object_story_spec", {})
            page_id = oss.get("page_id")
            ig_id = oss.get("instagram_actor_id")
            if page_id or ig_id:
                pages_from_ads.append({
                    "page_id": page_id,
                    "instagram_actor_id": ig_id,
                })
        results["method4_pages_from_existing_ads"] = pages_from_ads
    except Exception as ex:
        results["method4_error"] = str(ex)

    # Méthode 5 : instagram accounts du compte pub
    try:
        ig = list(account.get_instagram_accounts(fields=["id", "username"]))
        results["method5_instagram_accounts"] = [
            {"id": i["id"], "name": i.get("username")} for i in ig
        ]
    except Exception as ex:
        results["method5_error"] = str(ex)

    # Méthode 6 : Instagram accounts via la Page
    # (les comptes Instagram sont souvent liés à la Page, pas au compte pub)
    try:
        # Utiliser le page_id trouvé par la méthode 4
        if results.get("method4_pages_from_existing_ads"):
            found_page_id = results["method4_pages_from_existing_ads"][0][
                "page_id"
            ]
            from facebook_business.adobjects.page import Page

            page = Page(found_page_id)
            ig_from_page = list(
                page.get_instagram_accounts(
                    fields=["id", "username", "profile_pic"]
                )
            )
            results["method6_instagram_via_page"] = [
                {"id": i["id"], "username": i.get("username")}
                for i in ig_from_page
            ]
    except Exception as ex:
        results["method6_error"] = str(ex)

    # Méthode 7 : Instagram business account lié à la Page
    try:
        if results.get("method4_pages_from_existing_ads"):
            found_page_id = results["method4_pages_from_existing_ads"][0][
                "page_id"
            ]
            from facebook_business.adobjects.page import Page

            page = Page(found_page_id)
            page_data = page.api_get(fields=["instagram_business_account"])
            ig_biz = page_data.get("instagram_business_account")
            results["method7_instagram_business_account"] = {
                "id": ig_biz["id"] if ig_biz else None
            }
    except Exception as ex:
        results["method7_error"] = str(ex)

    # Méthode 8 : Instagram accounts via le Business Manager
    try:
        from facebook_business.adobjects.business import Business

        business_id = get_meta_api()
        business = Business(business_id)
        ig_bm = list(
            business.get_instagram_accounts(fields=["id", "username"])
        )
        results["method8_instagram_via_business"] = [
            {"id": i["id"], "username": i.get("username")} for i in ig_bm
        ]
    except Exception as ex:
        results["method8_error"] = str(ex)

    return [TextContent(type="text", text=json.dumps(
        results, ensure_ascii=False, indent=2))]
