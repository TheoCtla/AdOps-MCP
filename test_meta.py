"""Test d'authentification Meta Ads — liste les comptes publicitaires du Business Manager."""

import os
import sys

from dotenv import load_dotenv
from facebook_business.adobjects.business import Business
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError


# Mapping des statuts de compte publicitaire Meta vers un libellé lisible.
# Source : https://developers.facebook.com/docs/marketing-api/reference/ad-account/
ACCOUNT_STATUS = {
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

ACCOUNT_FIELDS = ["id", "name", "account_status", "currency", "timezone_name"]

REQUIRED_VARS = [
    "META_APP_ID",
    "META_APP_SECRET",
    "META_ACCESS_TOKEN",
    "META_BUSINESS_ID",
]


def load_config() -> dict:
    """Charge le .env et vérifie la présence des variables Meta requises."""
    load_dotenv()
    missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]
    if missing:
        print("Variables manquantes dans .env :")
        for var in missing:
            print(f"  - {var}")
        print("\nCopie .env.example en .env et remplis les valeurs.")
        sys.exit(1)
    return {var: os.environ[var] for var in REQUIRED_VARS}


def format_status(status_code) -> str:
    try:
        return ACCOUNT_STATUS.get(int(status_code), f"UNKNOWN({status_code})")
    except (TypeError, ValueError):
        return f"UNKNOWN({status_code})"


def print_accounts(title: str, accounts: list) -> None:
    print(f"\n=== {title} ({len(accounts)}) ===")
    if not accounts:
        print("  (aucun compte)")
        return

    header = f"{'ID':<22} | {'Nom':<35} | {'Status':<20} | {'Currency':<8} | TZ"
    print(header)
    print("-" * len(header))
    for acc in accounts:
        acc_id = acc.get("id", "")
        name = (acc.get("name") or "")[:35]
        status = format_status(acc.get("account_status"))
        currency = acc.get("currency", "")
        tz = acc.get("timezone_name", "")
        print(f"{acc_id:<22} | {name:<35} | {status:<20} | {currency:<8} | {tz}")


def handle_facebook_error(err: FacebookRequestError) -> None:
    """Traduit les codes d'erreur Meta les plus courants en messages actionnables."""
    code = err.api_error_code()
    subcode = err.api_error_subcode()
    message = err.api_error_message()

    if code == 190:
        print("[ERREUR] Access token invalide ou expiré.")
        print("→ Régénère un System User Token dans le Business Manager")
        print("  (Paramètres business > Utilisateurs système > Générer un nouveau token).")
    elif code == 200 or subcode == 10 or code == 10:
        print("[ERREUR] Permissions insuffisantes sur le token.")
        print("→ Vérifie que le System User Token a bien les permissions")
        print("  'ads_read' et 'business_management', et qu'il est associé au Business Manager.")
    else:
        print(f"[ERREUR Meta] code={code} subcode={subcode}")
        print(f"Message : {message}")
        print(f"Détail complet : {err.body()}")

    sys.exit(1)


def main() -> None:
    cfg = load_config()

    FacebookAdsApi.init(
        app_id=cfg["META_APP_ID"],
        app_secret=cfg["META_APP_SECRET"],
        access_token=cfg["META_ACCESS_TOKEN"],
    )

    business = Business(cfg["META_BUSINESS_ID"])

    try:
        owned = list(business.get_owned_ad_accounts(fields=ACCOUNT_FIELDS))
        clients = list(business.get_client_ad_accounts(fields=ACCOUNT_FIELDS))
    except FacebookRequestError as err:
        handle_facebook_error(err)
        return  # unreachable, pour mypy

    print_accounts("Comptes détenus (owned_ad_accounts)", owned)
    print_accounts("Comptes clients (client_ad_accounts)", clients)

    total = len(owned) + len(clients)
    print(f"\nTotal : {total} compte(s) ({len(owned)} détenu(s), {len(clients)} client(s))")
    print("Authentification Meta OK.")


if __name__ == "__main__":
    main()
