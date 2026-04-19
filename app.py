"""
app.py

File principale Flask.

Cosa fa:
- avvia il server web locale
- espone endpoint locali /api/...
- usa solar_client.py per chiamare il portale remoto
- usa db.py per salvare token e risposte JSON in SQLite
"""

import os
import threading
import time
from utility import get_logger

from flask import Flask, jsonify, request
from db import init_db, get_last_token_row, get_last_user_info_row
from solar_client import SolarClient


logger = get_logger("app")

app = Flask(__name__)
client = SolarClient()


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/api/login", methods=["POST", "GET"])
def login():
    try:
        data = client.do_login()
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/token/latest", methods=["GET"])
def token_latest():
    try:
        row = get_last_token_row()
        return jsonify({"ok": True, "row": row})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/user-info", methods=["GET"])
def user_info():
    try:
        data = client.get_user_info(save_to_db=True)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/user-info/latest", methods=["GET"])
def user_info_latest():
    try:
        row = get_last_user_info_row()
        return jsonify({"ok": True, "row": row})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/device-state/latest", methods=["GET"])
def device_state_latest():
    try:
        device_id = request.args.get("deviceId")
        data_source = int(request.args.get("dataSource", "1"))

        if not device_id:
            return jsonify({"ok": False, "error": "Parametro deviceId mancante"}), 400

        data = client.get_device_state_latest(
            device_id=device_id,
            data_source=data_source,
            save_to_db=True,
        )
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def polling_loop():
    device_id = os.getenv("DEVICE_ID", "416360187241136128")
    data_source = int(os.getenv("DEVICE_DATA_SOURCE", "1"))
    interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    logger.info(
        "Polling loop avviato | device_id=%s | data_source=%s | interval_seconds=%s",
        device_id,
        data_source,
        interval_seconds,
    )

    while True:
        try:
            logger.info("Polling START")
            client.get_device_state_latest(
                device_id=device_id,
                data_source=data_source,
                save_to_db=True,
            )
            logger.info("Polling OK")
        except Exception as e:
            logger.exception("Polling ERROR | error=%s", e)

        time.sleep(interval_seconds)


def start_background_polling():
    enabled = os.getenv("ENABLE_BACKGROUND_POLLING", "1") == "1"
    if not enabled:
        logger.info("Background polling disabilitato")
        return

    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()
    logger.info("Thread background polling avviato")

if __name__ == "__main__":
    init_db()
    start_background_polling()  
    app.run(host="0.0.0.0", port=5000, debug=False)