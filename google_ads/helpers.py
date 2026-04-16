"""Helpers partagés entre les tools MCP Google Ads.

Ce module regroupe les utilitaires que plusieurs tools utilisent :
enveloppage des erreurs, normalisation des enums et des IDs, arrondis
métiers, formatage des exceptions Google Ads. Les fonctions sont
publiques (pas d'underscore) car elles sont importées par les tools ;
les vraies privées (constantes internes) gardent le préfixe ``_``.
"""

from __future__ import annotations

import json
from typing import Any

from google.ads.googleads.errors import GoogleAdsException
from mcp.types import TextContent


# Buckets d'enum renvoyés par l'API Google Ads quand une valeur n'est pas
# calculée ou non applicable : on les convertit en ``None`` côté JSON pour
# ne pas polluer l'output avec un string trompeur.
_UNKNOWN_ENUM_NAMES = {"UNSPECIFIED", "UNKNOWN"}

# Statuts de campagne / ad group / ad acceptés par les tools de performance.
# Mutualisé entre campaign_performance, adgroup_performance et ads.
ALLOWED_PERF_STATUSES = frozenset({"ENABLED", "PAUSED", "REMOVED"})


def error_payload(message: str) -> list[TextContent]:
    """Enveloppe un message d'erreur dans un ``TextContent`` JSON MCP.

    Tous les handlers retournent ``list[TextContent]`` ; en cas d'erreur
    métier, on renvoie un JSON ``{"error": "..."}`` que Claude peut
    reformuler pour l'utilisateur sans exposer de stacktrace.
    """
    return [TextContent(type="text", text=json.dumps({"error": message}, ensure_ascii=False))]


def enum_name(value: Any) -> str:
    """Retourne le nom d'un enum proto-plus, ou sa représentation string en fallback."""
    name = getattr(value, "name", None)
    return name if name else str(value)


def nullable_enum(value: Any) -> str | None:
    """Retourne le nom de l'enum ou ``None`` si la valeur est UNKNOWN/UNSPECIFIED.

    Utile pour les champs comme ``quality_info.*`` ou ``ad_strength`` qui
    encodent « non calculé / non applicable » via le bucket UNKNOWN — on
    préfère un ``null`` JSON à un string trompeur côté client.
    """
    name = enum_name(value)
    return None if name in _UNKNOWN_ENUM_NAMES else name


def clean_customer_id(raw: Any) -> str:
    """Valide et nettoie un ``customer_id`` (10 chiffres, sans tirets).

    Lève ``ValueError`` avec un message français actionnable si l'entrée
    n'est pas exploitable. Les tirets saisis par habitude
    (``123-456-7890``) sont retirés silencieusement.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            "Paramètre 'customer_id' requis (10 chiffres, sans tirets). "
            "Utilise google_ads_list_accounts pour le trouver."
        )
    cleaned = raw.replace("-", "").strip()
    if not cleaned.isdigit() or len(cleaned) != 10:
        raise ValueError(
            f"customer_id invalide : '{raw}'. Attendu : 10 chiffres "
            "(ex. '1234567890'). Utilise google_ads_list_accounts pour le trouver."
        )
    return cleaned


def numeric_id(raw: Any, field_name: str) -> str:
    """Valide qu'un ID optionnel (campaign_id, ad_group_id) est numérique.

    Retourne une string vide si ``raw`` est ``None`` (ID absent = pas de
    filtre). Lève ``ValueError`` si fourni mais non numérique.
    """
    if raw is None:
        return ""
    if not isinstance(raw, (str, int)):
        raise ValueError(f"{field_name} doit être une chaîne numérique.")
    s = str(raw).strip()
    if not s.isdigit():
        raise ValueError(
            f"{field_name} invalide : '{raw}'. Attendu : ID numérique Google Ads."
        )
    return s


def escape_gaql_string(value: str) -> str:
    """Échappe les single-quotes pour une valeur string interpolée dans GAQL.

    GAQL double les simple-quotes pour les échapper (``l'ami`` → ``l''ami``).
    Indispensable dès qu'on concatène une chaîne utilisateur dans une query.
    """
    return value.replace("'", "''")


def round_money(value: float | int | None) -> float | None:
    """Arrondit un montant en euros à 2 décimales (``None`` si ``None``)."""
    if value is None:
        return None
    return round(float(value), 2)


def round_ratio(value: float | int | None) -> float | None:
    """Arrondit un ratio à 4 décimales (``None`` si ``None``)."""
    if value is None:
        return None
    return round(float(value), 4)


def parse_ad_text_assets(assets: Any) -> list[dict[str, Any]]:
    """Convertit une liste d'``AdTextAsset`` (RSA headlines/descriptions) en dicts.

    Chaque asset RSA a un ``text`` et un ``pinned_field`` (enum) qui indique
    s'il est pinné sur une position précise (HEADLINE_1/2/3, DESCRIPTION_1/2).
    Les assets non pinnés renvoient ``UNSPECIFIED`` — on le normalise en
    ``None`` pour l'output JSON.
    """
    result: list[dict[str, Any]] = []
    for asset in assets:
        text = asset.text if asset.text else ""
        pinned_raw = enum_name(asset.pinned_field)
        pinned = pinned_raw if pinned_raw not in _UNKNOWN_ENUM_NAMES else None
        result.append({"text": text, "pinned": pinned})
    return result


def format_google_ads_error(ex: GoogleAdsException) -> str:
    """Transforme une ``GoogleAdsException`` en message français actionnable.

    Distingue les erreurs d'authentification (refresh token expiré) et
    d'autorisation (MCC mal configuré) pour orienter le debug ; pour les
    autres, renvoie le détail champ-par-champ avec le ``request_id``.
    """
    auth_error = False
    authz_error = False
    details: list[str] = []

    for error in ex.failure.errors:
        code = error.error_code
        if code.authentication_error:
            auth_error = True
        if code.authorization_error:
            authz_error = True
        field_path = ""
        if error.location and error.location.field_path_elements:
            field_path = ".".join(el.field_name for el in error.location.field_path_elements)
        details.append(f"[{field_path or '-'}] {error.message}")

    if auth_error:
        return (
            "Refresh token Google Ads invalide ou expiré. "
            "Régénère-le avec le compte Google qui a accès au MCC."
        )
    if authz_error:
        return (
            "Pas d'accès au MCC Google Ads. Vérifie GOOGLE_ADS_LOGIN_CUSTOMER_ID "
            "et que le compte Google du refresh token est bien invité sur ce MCC."
        )

    return (
        f"Erreur Google Ads (request_id={ex.request_id}) : " + " | ".join(details)
        if details
        else f"Erreur Google Ads (request_id={ex.request_id})."
    )
