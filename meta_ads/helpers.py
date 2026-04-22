"""Helpers partagés entre les tools MCP Meta Ads."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from mcp.types import TextContent


def default_date_range(days_back: int = 7) -> tuple[str, str]:
    """Retourne ``(date_from, date_to)`` au format ``YYYY-MM-DD``.

    ``date_to`` = hier (métriques du jour partiel), ``date_from`` =
    ``date_to - days_back``.
    """
    today = date.today()
    date_to = today - timedelta(days=1)
    date_from = date_to - timedelta(days=days_back)
    return date_from.isoformat(), date_to.isoformat()


def error_payload(message: str) -> list[TextContent]:
    """Enveloppe un message d'erreur dans un ``TextContent`` JSON MCP."""
    return [TextContent(type="text", text=json.dumps({"error": message}, ensure_ascii=False))]


def format_meta_error(ex: Exception) -> str:
    """Transforme une exception Meta API en message français actionnable."""
    from facebook_business.exceptions import FacebookRequestError

    if isinstance(ex, FacebookRequestError):
        code = ex.api_error_code()
        msg = ex.api_error_message()
        if code == 190:
            return (
                "Access token Meta expiré ou invalide. "
                "Régénère un System User Token dans le Business Manager."
            )
        if code in (17, 32):
            return "Rate limit Meta atteint. Réessaye dans quelques minutes."
        if code in (10, 200):
            return (
                "Permissions insuffisantes sur ce compte. "
                f"Vérifie les accès du System User. [Meta: {msg}]"
            )
        if code == 100:
            return f"Paramètre invalide. [Meta: {msg}]"
        return f"Erreur Meta (code {code}) : {msg}"
    return f"Erreur inattendue : {type(ex).__name__} — {ex}"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convertit une valeur Meta en float, gère None et strings."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def euros_to_cents(euros: float) -> int:
    """Convertit des euros en centimes Meta (arrondi entier)."""
    return int(round(euros * 100))


def cents_to_euros(cents: int | str | None) -> float | None:
    """Convertit les centimes Meta en euros.

    Meta exprime les budgets (daily_budget, lifetime_budget) en centimes
    de la devise du compte. ``5000`` centimes = ``50.00`` euros.
    """
    if cents is None:
        return None
    return round(float(cents) / 100, 2)


def parse_actions(actions: list[dict[str, Any]] | None, action_type: str) -> float:
    """Extrait une valeur spécifique du tableau ``actions`` de Meta.

    Le champ ``actions`` est un tableau
    ``[{"action_type": "lead", "value": "5"}, ...]``.
    """
    if not actions:
        return 0.0
    for action in actions:
        if action.get("action_type") == action_type:
            return safe_float(action.get("value"))
    return 0.0


def parse_cost_per_action(
    cost_per_actions: list[dict[str, Any]] | None,
    action_type: str,
) -> float | None:
    """Extrait le coût par action spécifique du tableau ``cost_per_action_type``."""
    if not cost_per_actions:
        return None
    for cpa in cost_per_actions:
        if cpa.get("action_type") == action_type:
            return safe_float(cpa.get("value"))
    return None


ACCOUNT_STATUS_MAP: dict[int, str] = {
    1: "ACTIVE",
    2: "DISABLED",
    3: "UNSETTLED",
    7: "PENDING_RISK_REVIEW",
    8: "PENDING_SETTLEMENT",
    9: "IN_GRACE_PERIOD",
    100: "PENDING_CLOSURE",
    101: "CLOSED",
    201: "ANY_ACTIVE",
    202: "ANY_CLOSED",
}
