"""Helpers de formatage pour les réponses Google Ads."""

from __future__ import annotations

from datetime import date, timedelta


def default_date_range(days_back: int = 7) -> tuple[str, str]:
    """Retourne un tuple ``(date_from, date_to)`` au format ``YYYY-MM-DD``.

    ``date_to`` est toujours hier (``today - 1 day``) : les métriques du jour
    en cours sont partielles côté Google Ads et induisent en erreur. ``date_from``
    est ``date_to - days_back``. Avec ``days_back=7`` (défaut), on obtient donc
    une fenêtre de 8 jours (J-8 à J-1 inclus) adaptée aux rapports
    hebdomadaires, et ``days_back=29`` produit la fenêtre J-30 → J-1 utile
    aux vues journalières mensuelles.
    """
    today = date.today()
    date_to = today - timedelta(days=1)
    date_from = date_to - timedelta(days=days_back)
    return date_from.isoformat(), date_to.isoformat()


def safe_ratio(
    numerator: int | float | None,
    denominator: int | float | None,
    decimals: int = 4,
) -> float | None:
    """Retourne ``numerator / denominator`` arrondi, ou ``None`` si non calculable.

    Retourne ``None`` dès que le dénominateur vaut 0 ou ``None`` (un ratio
    sans dénominateur n'existe pas — ``0`` mentirait en laissant croire à
    une valeur mesurée). Retourne également ``None`` si le numérateur est
    ``None``. C'est ce que fait l'interface Google Ads (affichage ``"--"``).

    Utilisé pour tous les ratios dérivés : CTR, avg_cpc, CPA, ROAS.
    """
    if denominator is None or denominator == 0:
        return None
    if numerator is None:
        return None
    return round(numerator / denominator, decimals)


def micros_to_euros(micros: int | float | None) -> float | None:
    """Convertit un montant en micros (1/1_000_000) en euros arrondis à 2 décimales.

    Google Ads exprime tous les montants monétaires en micros pour éviter les
    erreurs de virgule flottante. Retourne None si l'entrée est None.
    """
    if micros is None:
        return None
    return round(micros / 1_000_000, 2)


def parse_customer_id(resource_name: str | None) -> str:
    """Extrait le customer_id d'un resource_name Google Ads.

    Exemple : "customers/1234567890" -> "1234567890".
    """
    if not resource_name:
        return ""
    return resource_name.split("/")[-1]
