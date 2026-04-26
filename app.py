import os
import threading
import time

from flask import Flask
from solar_client import SolarClient
from logger import get_logger
from zoneinfo import ZoneInfo
from datetime import datetime
from polling_tasks import acquire_and_save_inverter_state, check_and_set_bms_communication, check_registered_devices_on_lan, acquire_and_save_sensors_data, check_and_refresh_tesla_token

logger = get_logger("app")
app = Flask(__name__)
client = SolarClient()


def now_rome():
    return datetime.now(ZoneInfo("Europe/Rome"))


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
            logger.info("##################################################################")
            logger.info("##################### Polling START ##############################")
            logger.info("##################################################################")

            check_and_refresh_tesla_token(logger)
           
            data = acquire_and_save_inverter_state(client, logger, device_id, data_source)
           
            check_and_set_bms_communication(client, logger, device_id, data_source, interval_seconds, data)
            
            lan_result = check_registered_devices_on_lan(logger)

            found_count = 0
            if lan_result:
                found_count = int(lan_result.get("found_registered_count") or 0)

            if found_count > 0:
                acquire_and_save_sensors_data(logger, lan_result)
            else:
                logger.warning(
                    "[TASK] nuovo_task SKIP | nessun dispositivo LAN trovato | result=%s",
                    lan_result,
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