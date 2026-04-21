"""Authentification Meta Ads — singleton, initialise l'API une seule fois."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi


_REQUIRED_VARS = (
    "META_APP_ID",
    "META_APP_SECRET",
    "META_ACCESS_TOKEN",
    "META_BUSINESS_ID",
)

_initialized = False
_business_id: str | None = None


class MetaAdsConfigError(RuntimeError):
    """Variables d'environnement Meta Ads manquantes ou invalides."""


def get_meta_api() -> str:
    """Initialise l'API Meta Ads et retourne le Business Manager ID.

    Le premier appel lit le ``.env``, valide la config et appelle
    ``FacebookAdsApi.init()``. Les appels suivants retournent directement
    le ``business_id`` en cache.
    """
    global _initialized, _business_id
    if _initialized:
        return _business_id  # type: ignore[return-value]

    load_dotenv()

    missing = [var for var in _REQUIRED_VARS if not os.environ.get(var)]
    if missing:
        raise MetaAdsConfigError(
            "Variables Meta Ads manquantes dans .env : "
            + ", ".join(missing)
            + ". Copie .env.example en .env et remplis les valeurs."
        )

    FacebookAdsApi.init(
        app_id=os.environ["META_APP_ID"],
        app_secret=os.environ["META_APP_SECRET"],
        access_token=os.environ["META_ACCESS_TOKEN"],
    )

    _business_id = os.environ["META_BUSINESS_ID"]
    _initialized = True
    return _business_id
