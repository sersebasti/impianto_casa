# -----------------------------------------------------------------------------
# Flusso OAuth Tesla - Authorization Code
# -----------------------------------------------------------------------------
#
# Endpoint Tesla usati:
#
# 1) Autorizzazione via browser:
#
#    https://auth.tesla.com/oauth2/v3/authorize
#
# 2) Scambio code -> token:
#
#    https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token
#
# 3) Fleet API Europa:
#
#    https://fleet-api.prd.eu.vn.cloud.tesla.com
#
# Callback registrato nella console Tesla:
#
#    https://esprimo-flask.sersebasti.com/callback
#
# URL manuale da aprire nel browser/incognito:
#
#    https://auth.tesla.com/oauth2/v3/authorize?response_type=code&client_id=TUO_CLIENT_ID&redirect_uri=https%3A%2F%2Fesprimo-flask.sersebasti.com%2Fcallback&scope=openid%20offline_access%20user_data%20vehicle_device_data%20vehicle_cmds%20vehicle_charging_cmds&audience=https%3A%2F%2Ffleet-api.prd.eu.vn.cloud.tesla.com&state=test-nuovo-001&prompt=login
#
# Schema:
#
# 1) Apri l'URL manuale nel browser.
# 2) Tesla richiama:
#
#    https://esprimo-flask.sersebasti.com/callback?code=CODICE_GENERATO_DA_TESLA&issuer=https%3A%2F%2Fauth.tesla.com%2Foauth2%2Fv3&state=test-nuovo-001
#
# 3) Il nostro endpoint /callback chiama exchange_code_for_token(code).
#
# 4) exchange_code_for_token invia una POST a:
#
#    https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token
#
#    con payload x-www-form-urlencoded:
#
#    grant_type=authorization_code
#    client_id=TESLA_CLIENT_ID
#    client_secret=TESLA_CLIENT_SECRET
#    code=CODICE_GENERATO_DA_TESLA
#    redirect_uri=https://esprimo-flask.sersebasti.com/callback
#    scope=openid vehicle_device_data vehicle_cmds vehicle_charging_cmds offline_access user_data
#    audience=https://fleet-api.prd.eu.vn.cloud.tesla.com
#
# 5) Tesla restituisce:
#
#    access_token
#    refresh_token
#    id_token
#    expires_in
#    token_type
#
# 6) Il risultato viene salvato in:
#
#    data/tesla_token.json
#
# Note importanti:
#
# - Il code è temporaneo e monouso.
# - Se viene riusato, Tesla risponde invalid_auth_code.
# - redirect_uri nella URL /authorize e nella POST /token deve essere identico.
# - access_token dura poche ore; nel test expires_in=28800, cioè 8 ore.
# - refresh_token serve per generare un nuovo access_token senza browser.
# - Il refresh_token Tesla è monouso/single-use: quando lo usi, Tesla restituisce
#   anche un nuovo refresh_token. Bisogna quindi sovrascrivere data/tesla_token.json.
# - Se il refresh_token non è più valido, bisogna rifare il login dal browser,
#   meglio in finestra anonima/incognito.
# -----------------------------------------------------------------------------


import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


TESLA_CALLBACK_FILE = Path("data/tesla_callback_code.json")
TESLA_TOKEN_FILE = Path("data/tesla_token.json")

TESLA_TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"


def now_rome_str():
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M:%S")


def load_callback_code() -> str:
    if not TESLA_CALLBACK_FILE.exists():
        raise RuntimeError(f"File callback non trovato: {TESLA_CALLBACK_FILE}")

    data = json.loads(TESLA_CALLBACK_FILE.read_text(encoding="utf-8"))
    code = data.get("code")

    if not code:
        raise RuntimeError("Code Tesla mancante nel file callback")

    return code


def exchange_code_for_token(code: str | None = None) -> dict:
    client_id = os.getenv("TESLA_CLIENT_ID", "")
    client_secret = os.getenv("TESLA_CLIENT_SECRET", "")
    redirect_uri = os.getenv(
        "TESLA_REDIRECT_URI",
        "https://esprimo-flask.sersebasti.com/callback",
    )
    audience = os.getenv(
        "TESLA_AUDIENCE",
        "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    )

    if not client_id:
        raise RuntimeError("TESLA_CLIENT_ID mancante")
    if not client_secret:
        raise RuntimeError("TESLA_CLIENT_SECRET mancante")

    if code is None:
        code = load_callback_code()

    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": "openid vehicle_device_data vehicle_cmds vehicle_charging_cmds offline_access user_data",
        "audience": audience,
    }

    r = requests.post(
        TESLA_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    try:
        data = r.json()
    except Exception:
        data = {"raw_response": r.text}

    if r.status_code >= 400:
        raise RuntimeError(f"Errore token Tesla HTTP {r.status_code}: {data}")

    data["saved_at"] = now_rome_str()
    data["redirect_uri"] = redirect_uri
    data["audience"] = audience

    TESLA_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TESLA_TOKEN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return data



def refresh_tesla_token() -> dict:
    if not TESLA_TOKEN_FILE.exists():
        raise RuntimeError(f"File token non trovato: {TESLA_TOKEN_FILE}")

    token_data = json.loads(TESLA_TOKEN_FILE.read_text(encoding="utf-8"))
    refresh_token_value = token_data.get("refresh_token")

    if not refresh_token_value:
        raise RuntimeError("refresh_token non trovato in tesla_token.json")

    client_id = os.getenv("TESLA_CLIENT_ID", "")
    client_secret = os.getenv("TESLA_CLIENT_SECRET", "")
    audience = os.getenv(
        "TESLA_AUDIENCE",
        "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    )

    if not client_id:
        raise RuntimeError("TESLA_CLIENT_ID mancante")
    if not client_secret:
        raise RuntimeError("TESLA_CLIENT_SECRET mancante")

    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token_value,
        "scope": "openid vehicle_device_data vehicle_cmds vehicle_charging_cmds offline_access user_data",
        "audience": audience,
    }

    r = requests.post(
        TESLA_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    try:
        data = r.json()
    except Exception:
        data = {"raw_response": r.text}

    if r.status_code >= 400:
        raise RuntimeError(f"Errore refresh token Tesla HTTP {r.status_code}: {data}")

    data["saved_at"] = now_rome_str()
    data["audience"] = audience
    data["refreshed_from_saved_at"] = token_data.get("saved_at")

    # IMPORTANTISSIMO:
    # il refresh_token Tesla è monouso.
    # Qui sovrascriviamo subito il file con il NUOVO refresh_token.
    TESLA_TOKEN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return data


def load_access_token() -> str:
    if not TESLA_TOKEN_FILE.exists():
        raise RuntimeError(f"File token non trovato: {TESLA_TOKEN_FILE}")

    data = json.loads(TESLA_TOKEN_FILE.read_text(encoding="utf-8"))
    token = data.get("access_token")

    if not token:
        raise RuntimeError("access_token mancante")

    return token


def tesla_proxy_command(vin: str, command: str, payload: dict | None = None) -> dict:
    payload = payload or {}

    token = load_access_token()

    proxy_base = os.getenv(
        "TESLA_PROXY_BASE_URL",
        "https://tesla_http_proxy:4443",
    ).rstrip("/")

    url = f"{proxy_base}/api/1/vehicles/{vin}/command/{command}"

    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        verify=False,
        timeout=30,
    )

    try:
        data = r.json()
    except Exception:
        data = {"raw_response": r.text}

    if r.status_code >= 400:
        raise RuntimeError(f"Errore proxy Tesla HTTP {r.status_code}: {data}")

    return data


def wake_up_vehicle(vin: str) -> dict:
    token = load_access_token()

    proxy_base = os.getenv(
        "TESLA_PROXY_BASE_URL",
        "https://tesla_http_proxy:4443",
    ).rstrip("/")

    url = f"{proxy_base}/api/1/vehicles/{vin}/wake_up"

    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={},
        verify=False,
        timeout=30,
    )

    try:
        data = r.json()
    except Exception:
        data = {"raw_response": r.text}

    if r.status_code >= 400:
        raise RuntimeError(f"Errore wake_up Tesla HTTP {r.status_code}: {data}")

    return data