"""Test d'authentification Google Ads — liste les comptes sous le MCC (login_customer_id)."""

import os
import sys

from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


REQUIRED_VARS = [
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
]

GAQL_QUERY = """
    SELECT
      customer_client.client_customer,
      customer_client.descriptive_name,
      customer_client.status,
      customer_client.currency_code,
      customer_client.time_zone,
      customer_client.manager
    FROM customer_client
    WHERE customer_client.status = 'ENABLED'
"""


def load_config() -> dict:
    """Charge le .env et vérifie la présence des variables Google Ads requises."""
    load_dotenv()
    missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]
    if missing:
        print("Variables manquantes dans .env :")
        for var in missing:
            print(f"  - {var}")
        print("\nCopie .env.example en .env et remplis les valeurs.")
        sys.exit(1)

    # Nettoie l'ID MCC (l'API refuse les tirets).
    login_customer_id = os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"].replace("-", "").strip()

    return {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": login_customer_id,
        "use_proto_plus": True,
    }


def extract_customer_id(resource_name: str) -> str:
    """'customers/1234567890' -> '1234567890'."""
    return resource_name.split("/")[-1] if resource_name else ""


def print_accounts(title: str, accounts: list) -> None:
    print(f"\n=== {title} ({len(accounts)}) ===")
    if not accounts:
        print("  (aucun compte)")
        return

    header = f"{'ID':<12} | {'Nom':<35} | {'Currency':<8} | {'TZ':<25} | Manager"
    print(header)
    print("-" * len(header))
    for acc in accounts:
        name = (acc["name"] or "")[:35]
        print(
            f"{acc['id']:<12} | {name:<35} | {acc['currency']:<8} | "
            f"{acc['tz']:<25} | {'oui' if acc['manager'] else 'non'}"
        )


def handle_google_ads_error(ex: GoogleAdsException) -> None:
    """Traduit les erreurs Google Ads les plus courantes en messages actionnables."""
    auth_error = False
    authz_error = False

    for error in ex.failure.errors:
        code = error.error_code
        if code.authentication_error:
            auth_error = True
        if code.authorization_error:
            authz_error = True

    if auth_error:
        print("[ERREUR] Refresh token invalide ou expiré.")
        print("→ Régénère-le avec le compte Google qui a accès au MCC")
        print("  (via OAuth Playground ou le script officiel generate_user_credentials).")
    elif authz_error:
        print("[ERREUR] Pas d'accès au MCC (login_customer_id).")
        print("→ Vérifie GOOGLE_ADS_LOGIN_CUSTOMER_ID et que le compte Google du refresh token")
        print("  est bien invité sur ce MCC avec les droits nécessaires.")
    else:
        print(f"[ERREUR Google Ads] request_id={ex.request_id}")
        for i, error in enumerate(ex.failure.errors, 1):
            field_path = ""
            if error.location and error.location.field_path_elements:
                field_path = ".".join(
                    el.field_name for el in error.location.field_path_elements
                )
            print(f"  {i}. field={field_path or '-'} | message={error.message}")

    sys.exit(1)


def main() -> None:
    cfg = load_config()
    client = GoogleAdsClient.load_from_dict(cfg)
    ga_service = client.get_service("GoogleAdsService")

    try:
        response = ga_service.search(
            customer_id=cfg["login_customer_id"],
            query=GAQL_QUERY,
        )
        rows = []
        for row in response:
            cc = row.customer_client
            rows.append(
                {
                    "id": extract_customer_id(cc.client_customer),
                    "name": cc.descriptive_name,
                    "currency": cc.currency_code,
                    "tz": cc.time_zone,
                    "manager": cc.manager,
                }
            )
    except GoogleAdsException as ex:
        handle_google_ads_error(ex)
        return  # unreachable

    managers = [r for r in rows if r["manager"]]
    clients = [r for r in rows if not r["manager"]]

    print_accounts("Comptes MANAGER (MCC intermédiaires)", managers)
    print_accounts("Comptes CLIENT (comptes finaux)", clients)

    print(
        f"\nTotal : {len(rows)} compte(s) "
        f"({len(managers)} manager(s), {len(clients)} client(s))"
    )
    print("Authentification Google Ads OK.")


if __name__ == "__main__":
    main()
