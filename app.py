import os
import threading
import time

from flask import Flask
from flask_cors import CORS
from solar_client import SolarClient
from logger import get_logger
from zoneinfo import ZoneInfo
from datetime import datetime
from polling_tasks import acquire_and_save_inverter_state, check_and_set_bms_communication, check_registered_devices_on_lan, acquire_and_save_sensors_status_data, check_and_refresh_tesla_token, acquire_and_save_sensors_measurements_data, acquire_and_save_relays_status_data

logger = get_logger("app")
app = Flask(__name__)
CORS(app)
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

            logger.info("")
            logger.info("##################################################################")
            logger.info("######################## POLLING START ###########################")
            logger.info("##################################################################")

            ##################################################################
            # TESLA TOKEN
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("######################## TESLA TOKEN #############################")
            logger.info("##################################################################")

            logger.info("[STEP START] Tesla token check")

            check_and_refresh_tesla_token(
                logger
            )

            logger.info("[STEP END] Tesla token check")

            ##################################################################
            # INVERTER STATE
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("#################### INVERTER STATE ##############################")
            logger.info("##################################################################")

            logger.info("[STEP START] Inverter state acquisition")

            data = acquire_and_save_inverter_state(
                client,
                logger,
                device_id,
                data_source,
            )

            logger.info("[STEP END] Inverter state acquisition")

            ##################################################################
            # BMS CONTROL
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("######################## BMS CONTROL #############################")
            logger.info("##################################################################")

            logger.info("[STEP START] BMS control")

            check_and_set_bms_communication(
                client,
                logger,
                device_id,
                data_source,
                interval_seconds,
                data,
            )

            logger.info("[STEP END] BMS control")

            ##################################################################
            # LAN DEVICES CHECK
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("###################### LAN DEVICES CHECK #########################")
            logger.info("##################################################################")

            logger.info("[STEP START] LAN devices check")

            lan_result = check_registered_devices_on_lan(
                logger
            )

            found_count = 0

            if lan_result:

                found_count = int(
                    lan_result.get(
                        "found_registered_count"
                    ) or 0
                )

            logger.info(
                "[STEP END] LAN devices check | found_count=%s",
                found_count,
            )

            ##################################################################
            # SENSOR STATUS SNAPSHOTS
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("################### SENSOR STATUS SNAPSHOTS #####################")
            logger.info("##################################################################")

            if found_count > 0:

                logger.info(
                    "[STEP START] Sensor status acquisition"
                )

                status_ok = (
                    acquire_and_save_sensors_status_data(
                        logger
                    )
                )

                if status_ok:

                    logger.info(
                        "[STEP END] Sensor status acquisition OK"
                    )

                else:

                    logger.error(
                        "[STEP END] Sensor status acquisition FAILED"
                    )

            else:

                logger.warning(
                    "[STEP SKIPPED] Sensor status acquisition | "
                    "nessun dispositivo LAN trovato"
                )

            ##################################################################
            # RELAYS STATUS SNAPSHOTS
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("################### RELAYS STATUS SNAPSHOTS #####################")
            logger.info("##################################################################")

            relay_result = None

            relay1_real_state = None

            if found_count > 0:

                logger.info(
                    "[STEP START] Relay status acquisition"
                )

                relay_result = (
                    acquire_and_save_relays_status_data(
                        logger
                    )
                )

                if (
                    relay_result
                    and relay_result.get("ok")
                ):

                    relay1_real_state = (
                        relay_result
                        .get(
                            "relay_state_summary",
                            {},
                        )
                        .get(
                            "relay1_real_state"
                        )
                    )

                    logger.info(
                        "[STEP END] Relay status acquisition OK | "
                        "relay1_real_state=%s",
                        relay1_real_state,
                    )

                else:

                    logger.error(
                        "[STEP END] Relay status acquisition FAILED"
                    )

            else:

                logger.warning(
                    "[STEP SKIPPED] Relay status acquisition | "
                    "nessun dispositivo LAN trovato"
                )

            ##################################################################
            # SENSOR MEASUREMENTS SNAPSHOTS
            ##################################################################

            logger.info("")
            logger.info("##################################################################")
            logger.info("################ SENSOR MEASUREMENTS SNAPSHOTS ##################")
            logger.info("##################################################################")

            #
            # Measurements consentiti SOLO se:
            #
            # relay1_real_state == True
            #

            measurements_allowed = (
                relay1_real_state is not None
            )

            if (
                found_count > 0
                and measurements_allowed
            ):

                logger.info(
                    "[STEP START] Sensor measurements acquisition"
                )

                measurements_ok = (
                    acquire_and_save_sensors_measurements_data(
                        logger
                    )
                )

                if measurements_ok:

                    logger.info(
                        "[STEP END] Sensor measurements acquisition OK"
                    )

                else:

                    logger.error(
                        "[STEP END] Sensor measurements acquisition FAILED"
                    )

            else:

                logger.warning(
                    "[STEP SKIPPED] Sensor measurements acquisition | "
                    "relay1_real_state=%s | "
                    "found_count=%s",
                    relay1_real_state,
                    found_count,
                )

            logger.info("")
            logger.info("##################################################################")
            logger.info("######################### POLLING END ############################")
            logger.info("##################################################################")

        except Exception as e:

            logger.exception(
                "Polling ERROR | error=%s",
                e,
            )

        finally:

            logger.info("")
            logger.info("##################################################################")
            logger.info("######################## POLLING SLEEP ###########################")
            logger.info("##################################################################")

            logger.info(
                "[POLLING SLEEP] seconds=%s",
                interval_seconds,
            )

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