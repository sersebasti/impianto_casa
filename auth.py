"""
auth.py

Modulo dedicato all'autenticazione verso il portale Solar/Siseli.

Cosa fa:
- calcola hash MD5 e SHA256
- genera nonce casuale
- decifra OPEN_APP_SECRET_ENC
- costruisce la firma richiesta dal portale
- esegue il login con account/password
- restituisce sessione requests + token + JSON di risposta
"""

import base64
import hashlib
import hmac
import json
import os
import random
import string
from urllib.parse import parse_qsl, urlparse

import requests
from Crypto.Cipher import AES

from utility import get_logger, mask_token

logger = get_logger("auth")

BASE = os.getenv("INVERTER_BASE_URL", "https://solar.siseli.com").rstrip("/")
OPEN_APP_ID = os.getenv("OPEN_APP_ID", "")
OPEN_APP_SECRET_ENC = os.getenv("OPEN_APP_SECRET_ENC", "")
IOT_TIME_ZONE = os.getenv("IOT_TIME_ZONE", "Europe/Rome")


def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest().lower()


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest().lower()


def make_nonce_32() -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(32))


def decrypt_open_app_secret(open_app_id: str, open_app_secret_enc: str) -> str:
    md5_id = md5_hex(open_app_id)
    key = md5_id[:16].encode("utf-8")
    iv = md5_id[16:32].encode("utf-8")

    ciphertext = base64.b64decode(open_app_secret_enc)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    plain = cipher.decrypt(ciphertext)
    plain = plain.rstrip(b"\x00")  # ZeroPadding
    return plain.decode("utf-8").strip()


def build_sign_params(url: str, method: str, body_str: str | None) -> dict:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))

    for k in ("IOT-Open-AppID", "IOT-Open-Nonce", "IOT-Open-Sign", "IOT-Open-Body-Hash"):
        params.pop(k, None)

    body_hash = ""
    if method.strip().upper() != "GET" and isinstance(body_str, str):
        body_hash = sha256_hex(body_str)

    params["IOT-Open-Body-Hash"] = body_hash
    return params


def stringify_sorted_no_encode(params: dict) -> str:
    items = sorted(params.items(), key=lambda kv: kv[0])
    return "&".join(f"{k}={v}" for k, v in items)


def sign_request(
    url: str,
    method: str,
    body_str: str | None,
    open_app_id: str,
    open_app_secret_enc: str,
    nonce: str,
) -> tuple[str, str, str, str]:
    params = build_sign_params(url, method, body_str)
    params["IOT-Open-AppID"] = open_app_id
    params["IOT-Open-Nonce"] = nonce

    real_secret = decrypt_open_app_secret(open_app_id, open_app_secret_enc)

    qs = stringify_sorted_no_encode(params)
    qs_b64 = base64.b64encode(qs.encode("utf-8")).decode("ascii")

    hmac_bytes = hmac.new(
        real_secret.encode("utf-8"),
        qs_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    sign = hashlib.md5(hmac_bytes).hexdigest().lower()
    return sign, real_secret, qs, qs_b64


def login(account: str, password_plain: str, debug: bool = False) -> dict:
    if not account:
        logger.error("INVERTER_ACCOUNT mancante")
        raise RuntimeError("INVERTER_ACCOUNT mancante")
    if not password_plain:
        logger.error("INVERTER_PASSWORD mancante")
        raise RuntimeError("INVERTER_PASSWORD mancante")
    if not OPEN_APP_ID:
        logger.error("OPEN_APP_ID mancante")
        raise RuntimeError("OPEN_APP_ID mancante")
    if not OPEN_APP_SECRET_ENC:
        logger.error("OPEN_APP_SECRET_ENC mancante")
        raise RuntimeError("OPEN_APP_SECRET_ENC mancante")

    logger.info("Login remoto START | account=%s | base=%s", account, BASE)

    password_md5 = md5_hex(password_plain)

    url = f"{BASE}/apis/login/account"
    body_obj = {
        "account": account,
        "password": password_md5,
    }
    body_str = json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)

    nonce = make_nonce_32()
    sign, real_secret, qs, qs_b64 = sign_request(
        url=url,
        method="POST",
        body_str=body_str,
        open_app_id=OPEN_APP_ID,
        open_app_secret_enc=OPEN_APP_SECRET_ENC,
        nonce=nonce,
    )

    if debug:
        logger.info("DEBUG login | nonce=%s", nonce)
        logger.info("DEBUG login | qs=%s", qs)
        logger.info("DEBUG login | qs_b64=%s", qs_b64)
        logger.info("DEBUG login | sign=%s", sign)
        logger.info("DEBUG login | body_sha256=%s", sha256_hex(body_str))

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": BASE,
        "Referer": f"{BASE}/",
        "IOT-Open-AppID": OPEN_APP_ID,
        "IOT-Open-Nonce": nonce,
        "IOT-Open-Sign": sign,
        "IOT-Time-Zone": IOT_TIME_ZONE,
        "IOT-Token": "null",
    }

    s = requests.Session()
    r = s.post(url, data=body_str, headers=headers, timeout=30)

    logger.info("Login remoto HTTP END | status_code=%s", r.status_code)

    if debug:
        logger.info("DEBUG login | response_text=%s", r.text)

    r.raise_for_status()
    data = r.json()

    if data.get("code") != 0:
        logger.error("Login fallita | response_json=%s", data)
        raise RuntimeError(f"Login fallita: {data}")

    token_data = data["data"]

    logger.info(
        "Login remoto OK | access_token=%s | access_exp=%s | refresh_exp=%s",
        mask_token(token_data["accessToken"]),
        token_data.get("accessTokenWillExpiredAt"),
        token_data.get("refreshTokenWillExpiredAt"),
    )

    return {
        "session": s,
        "token": token_data["accessToken"],
        "access_token": token_data["accessToken"],
        "access_token_expires_at": token_data.get("accessTokenWillExpiredAt"),
        "refresh_token": token_data.get("refreshToken"),
        "refresh_token_expires_at": token_data.get("refreshTokenWillExpiredAt"),
        "login_json": data,
        "real_secret": real_secret,
    }