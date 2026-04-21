"""Tool: google_ads_add_label.

Crée un label (si nécessaire) et l'applique à une campagne, un ad group,
une annonce ou un keyword.
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
    escape_gaql_string,
    format_google_ads_error,
    numeric_id,
)
from google_ads.queries import LABEL_LOOKUP_QUERY


log = logging.getLogger(__name__)

TOOL_NAME = "google_ads_add_label"

_ALLOWED_RESOURCE_TYPES = frozenset({
    "CAMPAIGN", "AD_GROUP", "AD_GROUP_AD", "AD_GROUP_CRITERION",
})


TOOL_DEFINITION = Tool(
    name=TOOL_NAME,
    description=(
        "Create a label (if it doesn't exist) and apply it to a Google Ads campaign, ad "
        "group, ad, or keyword.\n"
        "\n"
        "Returns a JSON confirmation with whether the label was newly created, and the "
        "resource_name of the label assignment.\n"
        "\n"
        "Use this tool to organize and tag resources for easier management — e.g. label "
        "top-performing campaigns, flag keywords for review, or group resources by client "
        "project. The label is created automatically if it doesn't already exist. Use "
        "google_ads_get_labels to see existing labels. For AD_GROUP_AD or AD_GROUP_CRITERION "
        "resource types, ad_group_id is required to build the resource path.\n"
        "\n"
        "⚠️ This tool MODIFIES data. A label may be created and is applied to the target "
        "resource immediately."
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
            "label_name": {
                "type": "string",
                "description": "Label name. Created if it doesn't exist.",
            },
            "resource_type": {
                "type": "string",
                "enum": ["CAMPAIGN", "AD_GROUP", "AD_GROUP_AD", "AD_GROUP_CRITERION"],
                "description": "Type of resource to label.",
            },
            "resource_id": {
                "type": "string",
                "description": (
                    "ID of the resource to label (campaign_id, ad_group_id, "
                    "ad_id, or criterion_id depending on resource_type)."
                ),
            },
            "ad_group_id": {
                "type": "string",
                "description": (
                    "Required when resource_type is AD_GROUP_AD or "
                    "AD_GROUP_CRITERION (needed to build the resource path)."
                ),
            },
        },
        "required": ["customer_id", "label_name", "resource_type", "resource_id"],
        "additionalProperties": False,
    },
)


async def handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handler for google_ads_add_label."""
    args = arguments or {}

    try:
        customer_id = clean_customer_id(args.get("customer_id"))
        resource_id = numeric_id(args.get("resource_id"), "resource_id")
        ad_group_id = numeric_id(args.get("ad_group_id"), "ad_group_id")
    except ValueError as ex:
        return error_payload(str(ex))

    if not resource_id:
        return error_payload("Paramètre 'resource_id' requis.")

    label_name = args.get("label_name")
    if not isinstance(label_name, str) or not label_name.strip():
        return error_payload("Paramètre 'label_name' requis (texte non vide).")
    label_name = label_name.strip()

    resource_type = args.get("resource_type")
    if resource_type not in _ALLOWED_RESOURCE_TYPES:
        return error_payload(
            f"resource_type invalide : '{resource_type}'. "
            f"Valeurs : {', '.join(sorted(_ALLOWED_RESOURCE_TYPES))}."
        )

    if resource_type in ("AD_GROUP_AD", "AD_GROUP_CRITERION") and not ad_group_id:
        return error_payload(
            f"ad_group_id requis quand resource_type = '{resource_type}'."
        )

    try:
        client = get_google_ads_client()
    except GoogleAdsConfigError as ex:
        return error_payload(str(ex))

    ga_service = client.get_service("GoogleAdsService")

    # Step 1: lookup or create the label.
    label_created = False
    escaped_name = escape_gaql_string(label_name)
    query = LABEL_LOOKUP_QUERY.format(label_name=escaped_name)

    try:
        results = list(ga_service.search(customer_id=customer_id, query=query))
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))

    if results:
        label_resource_name = results[0].label.resource_name
    else:
        label_op_wrapper = client.get_type("MutateOperation")
        lbl_op = label_op_wrapper.label_operation
        lbl = lbl_op.create
        lbl.name = label_name

        try:
            resp = ga_service.mutate(
                customer_id=customer_id,
                mutate_operations=[label_op_wrapper],
            )
        except GoogleAdsException as ex:
            return error_payload(format_google_ads_error(ex))

        label_resource_name = (
            resp.mutate_operation_responses[0].label_result.resource_name
        )
        label_created = True

    # Step 2: apply the label to the resource.
    operation = client.get_type("MutateOperation")

    if resource_type == "CAMPAIGN":
        cl_op = operation.campaign_label_operation
        cl = cl_op.create
        cl.campaign = ga_service.campaign_path(customer_id, resource_id)
        cl.label = label_resource_name
    elif resource_type == "AD_GROUP":
        agl_op = operation.ad_group_label_operation
        agl = agl_op.create
        agl.ad_group = ga_service.ad_group_path(customer_id, resource_id)
        agl.label = label_resource_name
    elif resource_type == "AD_GROUP_AD":
        adl_op = operation.ad_group_ad_label_operation
        adl = adl_op.create
        adl.ad_group_ad = ga_service.ad_group_ad_path(
            customer_id, ad_group_id, resource_id,
        )
        adl.label = label_resource_name
    elif resource_type == "AD_GROUP_CRITERION":
        acl_op = operation.ad_group_criterion_label_operation
        acl = acl_op.create
        acl.ad_group_criterion = ga_service.ad_group_criterion_path(
            customer_id, ad_group_id, resource_id,
        )
        acl.label = label_resource_name

    try:
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=[operation],
        )
    except GoogleAdsException as ex:
        return error_payload(format_google_ads_error(ex))
    except Exception as ex:
        log.exception("Erreur inattendue dans google_ads_add_label")
        return error_payload(f"Erreur inattendue : {type(ex).__name__} — {ex}")

    if not response.mutate_operation_responses:
        return error_payload("La mutation n'a retourné aucune réponse.")

    payload = {
        "success": True,
        "action": "ADDED_LABEL",
        "label_name": label_name,
        "label_created": label_created,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "label_resource_name": label_resource_name,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
