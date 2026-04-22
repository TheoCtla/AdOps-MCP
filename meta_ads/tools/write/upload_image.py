"""Tool: meta_ads_upload_image.

Upload une image dans la bibliothèque du compte pub via URL publique.
Retourne l'image_hash nécessaire pour créer des ads.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

import requests
from mcp.types import TextContent, Tool

from meta_ads.auth import MetaAdsConfigError, get_meta_api
from meta_ads.helpers import error_payload, format_meta_error


log = logging.getLogger(__name__)

TOOL_NAME = "meta_ads_upload_image"


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Upload an image from a public URL into a Meta Ads account's creative library. "
        "Returns the image_hash needed to create ads via meta_ads_create_ad.\n"
        "\n"
        "Returns a JSON confirmation with the image_hash.\n"
        "\n"
        "Use this tool before creating ads that need a new image. Accepted formats: JPG, "
        "PNG. Max size: 30 MB. Recommended resolutions: 1080x1080 (square) or 1200x628 "
        "(landscape). The image_hash returned can be used in creative_spec when calling "
        "meta_ads_create_ad.\n"
        "\n"
        "⚠️ This tool MODIFIES data. An image is uploaded to the account's asset library."
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
            "image_url": {
                "type": "string",
                "description": (
                    "Public URL of the image to upload (JPG or PNG). "
                    "Must be accessible without authentication."
                ),
            },
        },
        "required": ["ad_account_id", "image_url"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for meta_ads_upload_image."""
    args = arguments or {}

    ad_account_id = args.get("ad_account_id")
    image_url = args.get("image_url")

    if not ad_account_id:
        return error_payload("Paramètre 'ad_account_id' requis.")
    if not image_url or not isinstance(image_url, str):
        return error_payload("Paramètre 'image_url' requis.")
    if not image_url.startswith(("http://", "https://")):
        return error_payload("image_url doit commencer par http:// ou https://.")

    try:
        get_meta_api()
    except MetaAdsConfigError as ex:
        return error_payload(str(ex))

    # Download the image to a temp file.
    tmp_path = None
    try:
        resp = requests.get(image_url, timeout=30)
        if resp.status_code != 200:
            return error_payload(
                f"Impossible de télécharger l'image : HTTP {resp.status_code}."
            )

        suffix = ".png" if "png" in image_url.lower() else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        # Upload to Meta.
        from facebook_business.adobjects.adimage import AdImage

        image = AdImage(parent_id=ad_account_id)
        image[AdImage.Field.filename] = tmp_path
        image.remote_create()

        image_hash = image[AdImage.Field.hash]
    except Exception as ex:
        log.exception("Erreur dans meta_ads_upload_image")
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
            return [TextContent(type="text", text=json.dumps(error_detail, ensure_ascii=False))]
        return error_payload(format_meta_error(ex))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    payload = {
        "success": True,
        "action": "UPLOADED_IMAGE",
        "image_hash": image_hash,
        "ad_account_id": ad_account_id,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
