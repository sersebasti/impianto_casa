import os
import threading
import time

from flask import Flask
from solar_client import SolarClient
from logger import get_logger
from zoneinfo import ZoneInfo
from datetime import datetime

logger = get_logger("app")
app = Flask(__name__)
client = SolarClient()


def now_rome():
    return datetime.now(ZoneInfo("Europe/Rome"))


def polling_loop():
    device_id = os.getenv("DEVICE_ID", "416360187241136128")
    data_source = int(os.getenv("DEVICE_DATA_SOURCE", "1"))
    interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    high_threshold = float(os.getenv("BMS_OFF_THRESHOLD", "53.5"))
    low_threshold = float(os.getenv("BMS_ON_THRESHOLD", "52.0"))

    logger.info(
        "Polling loop avviato | device_id=%s | data_source=%s | interval_seconds=%s | low_threshold=%s | high_threshold=%s",
        device_id,
        data_source,
        interval_seconds,
        low_threshold,
        high_threshold,
    )

    while True:
        try:
            logger.info("Polling START")

            # 1) Legge stato inverter / batteria
            data = client.get_device_state_latest(
                device_id=device_id,
                data_source=data_source,
                save_to_db=True,
            )

            payload_data = data.get("data", {}) or {}
            fields = payload_data.get("fields", {}) or {}
            battery_item = fields.get("batteryVoltage", {}) or {}

            raw_battery_voltage = battery_item.get("valueDisplay")
            if raw_battery_voltage is None:
                raw_battery_voltage = battery_item.get("value")

            try:
                battery_voltage = float(
                    str(raw_battery_voltage).replace("V", "").replace("v", "").strip()
                )
            except Exception:
                battery_voltage = None

            logger.info(
                "Polling OK | battery_voltage=%s | raw_battery_voltage=%s",
                battery_voltage,
                raw_battery_voltage,
            )

            if battery_voltage is None:
                logger.warning("Battery voltage non trovata o non convertibile")
                time.sleep(interval_seconds)
                continue

            # 2) Decide stato desiderato con isteresi
            # NUOVA MAPPA:
            # 1 = OFF
            # 2 = ON
            desired_bms_value = None

            if battery_voltage > high_threshold:
                desired_bms_value = "1"   # OFF

            elif battery_voltage < low_threshold:
                desired_bms_value = "2"   # ON

            if desired_bms_value is None:
                logger.info(
                    "BMS nessuna azione | battery_voltage=%s | fascia neutra [%s - %s]",
                    battery_voltage,
                    low_threshold,
                    high_threshold,
                )
                time.sleep(interval_seconds)
                continue

            # 3) Legge stato reale attuale dal portale
            status = client.get_bms_communication(device_id)
            status_data = status.get("data", {}) or {}

            current_bms_display = str(
                status_data.get("valueDisplay", "")
            ).strip().upper()

            # NUOVA MAPPA:
            # OFF -> 1
            # ON  -> 2
            if current_bms_display == "OFF":
                current_bms_value = "1"

            elif current_bms_display == "ON":
                current_bms_value = "2"

            else:
                current_bms_value = None

            logger.info(
                "BMS stato attuale | current_value=%s | current_display=%s | desired_value=%s",
                current_bms_value,
                current_bms_display,
                desired_bms_value,
            )

            # 4) Se già corretto non fare nulla
            if current_bms_value == desired_bms_value:
                logger.info(
                    "BMS già corretto | battery_voltage=%s | value=%s",
                    battery_voltage,
                    current_bms_value,
                )
                time.sleep(interval_seconds)
                continue

            # 5) Cambia stato
            logger.info(
                "BMS cambio stato START | battery_voltage=%s | old_value=%s | new_value=%s",
                battery_voltage,
                current_bms_value,
                desired_bms_value,
            )

            remote_data = client.set_bms_communication(
                device_id=device_id,
                value=desired_bms_value,
            )

            logger.info(
                "BMS cambio stato OK | battery_voltage=%s | new_value=%s | response=%s",
                battery_voltage,
                desired_bms_value,
                remote_data,
            )

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


from endpoints import bp
app.register_blueprint(bp)

if __name__ == "__main__":
    from db import init_db

    init_db()
    start_background_polling()
    app.run(host="0.0.0.0", port=5000, debug=False)