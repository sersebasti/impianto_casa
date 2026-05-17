import os
import json
import sqlite3
import requests


def execute_command_by_config_id(
    logger,
    config_id,
):

    db_path = os.getenv(
        "DB_PATH",
        "data/solar.db",
    )

    logger.info(
        "[COMMAND] START | config_id=%s",
        config_id,
    )

    conn = None

    try:

        ####################################################################
        # DB CONNECT
        ####################################################################

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        conn.row_factory = sqlite3.Row

        cur = conn.cursor()

        ####################################################################
        # LOAD CONFIG
        ####################################################################

        cur.execute(
            """
            SELECT *
            FROM sensor_measurements_config
            WHERE enabled = 1
              AND call_type = 'command'
              AND id = ?
            """,
            (
                config_id,
            )
        )

        row = cur.fetchone()

        if not row:

            raise RuntimeError(
                f"Command config non trovato: {config_id}"
            )

        cfg = dict(row)

        device_id = cfg["device_id"]

        endpoint_query = (
            cfg["endpoint_query"]
            or ""
        )

        http_method = (
            cfg["http_method"]
            or "POST"
        ).upper()

        description = (
            cfg["description"]
            or ""
        )

        payload_raw = cfg["payload"]

        logger.info(
            "[COMMAND] CONFIG LOADED | "
            "description=%s | "
            "device_id=%s | "
            "endpoint=%s | "
            "method=%s",
            description,
            device_id,
            endpoint_query,
            http_method,
        )

        ####################################################################
        # PAYLOAD
        ####################################################################

        payload = {}

        if payload_raw:

            try:

                payload = json.loads(
                    payload_raw
                )

            except Exception as e:

                raise RuntimeError(
                    f"Payload JSON non valido: {e}"
                )

        ####################################################################
        # URL
        ####################################################################

        url = (
            f"http://host.docker.internal:5001/"
            f"{device_id}/command"
            f"?endpoint={endpoint_query}"
        )

        logger.info(
            "[COMMAND] HTTP REQUEST | "
            "method=%s | "
            "url=%s | "
            "payload=%s",
            http_method,
            url,
            payload,
        )

        ####################################################################
        # HTTP CALL
        ####################################################################

        session = requests.Session()

        if http_method == "POST":

            response = session.post(
                url,
                json=payload,
                timeout=(5, 30),
            )

        elif http_method == "GET":

            response = session.get(
                url,
                timeout=(5, 30),
            )

        else:

            raise RuntimeError(
                f"Metodo HTTP non supportato: {http_method}"
            )

        logger.info(
            "[COMMAND] HTTP RESPONSE | "
            "status_code=%s",
            response.status_code,
        )

        response.raise_for_status()

        ####################################################################
        # JSON RESPONSE
        ####################################################################

        try:

            response_json = response.json()

        except Exception:

            response_json = {
                "raw_text": response.text
            }

        logger.info(
            "[COMMAND] RESPONSE JSON | %s",
            json.dumps(
                response_json,
                ensure_ascii=False,
            )
        )

        ####################################################################
        # RESULT
        ####################################################################

        return {
            "ok": True,
            "config_id": config_id,
            "description": description,
            "url": url,
            "http_method": http_method,
            "payload": payload,
            "response": response_json,
        }

    except Exception as e:

        logger.exception(e)

        return {
            "ok": False,
            "config_id": config_id,
            "error": str(e),
        }

    finally:

        try:

            if conn:
                conn.close()

        except:
            pass