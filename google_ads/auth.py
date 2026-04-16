"""Authentification Google Ads — une seule instance de client par processus."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient


_REQUIRED_VARS = (
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
)

# Singleton au niveau module — évite de reconstruire le client à chaque appel
# de tool (coûteux : chargement gRPC, résolution OAuth, etc.).
_client: GoogleAdsClient | None = None


class GoogleAdsConfigError(RuntimeError):
    """Variables d'environnement Google Ads manquantes ou invalides."""


def get_google_ads_client() -> GoogleAdsClient:
    """Retourne le client Google Ads partagé du processus.

    Le premier appel lit le `.env`, valide la config et instancie le client.
    Les appels suivants retournent l'instance cachée.
    """
    global _client
    if _client is not None:
        return _client

    load_dotenv()

    missing = [var for var in _REQUIRED_VARS if not os.environ.get(var)]
    if missing:
        raise GoogleAdsConfigError(
            "Variables Google Ads manquantes dans .env : "
            + ", ".join(missing)
            + ". Copie .env.example en .env et remplis les valeurs."
        )

    # L'API Google Ads refuse les tirets dans le login_customer_id.
    login_customer_id = os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"].replace("-", "").strip()

    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": login_customer_id,
        "use_proto_plus": True,
    }

    _client = GoogleAdsClient.load_from_dict(config)
    return _client
