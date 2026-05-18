import os
import requests
import time
import sqlite3
import json
from datetime import datetime, timezone
from tesla_client import refresh_tesla_token
from pathlib import Path


def acquire_and_save_inverter_state(client, logger, device_id, data_source):
    """
    Task: acquisisce lo stato inverter/batteria e lo salva nel DB.
    Restituisce il dict dei dati ottenuti.
    """
    logger.info("[TASK] acquire_and_save_inverter_state | device_id=%s | data_source=%s", device_id, data_source)
    data = client.get_device_state_latest(
        device_id=device_id,
        data_source=data_source,
        save_to_db=True,
    )
    logger.info("[TASK] acquire_and_save_inverter_state OK")
    return data


from datetime import datetime
import os


def check_and_set_bms_communication(client, logger, device_id, data_source, interval_seconds, data=None):
    """
    Task: verifica la tensione batteria e gestisce il comando BMS con isteresi.

    Logica:
    - Di giorno:
        battery_voltage > high_threshold -> BMS OFF = 1
        battery_voltage < low_threshold  -> BMS ON  = 2
    - Dalle BMS_NIGHT_ON_HOUR in poi:
        forza BMS ON = 2, così durante la notte puoi vedere il SOC.
    """

    high_threshold = float(os.getenv("BMS_OFF_THRESHOLD", "53.5"))
    low_threshold = float(os.getenv("BMS_ON_THRESHOLD", "52.0"))
    night_bms_on_hour = int(os.getenv("BMS_NIGHT_ON_HOUR", "22"))

    logger.info(
        "[TASK] check_and_set_bms_communication | low_threshold=%s | high_threshold=%s | night_bms_on_hour=%s",
        low_threshold,
        high_threshold,
        night_bms_on_hour,
    )

    # 0) Fascia sera/notte: forza BMS ON e termina
    now_hour = datetime.now().hour

    if now_hour >= night_bms_on_hour:
        status = client.get_bms_communication(device_id)
        status_data = status.get("data", {}) or {}
        current_bms_display = str(status_data.get("valueDisplay", "")).strip().upper()

        logger.info(
            "[TASK] Fascia sera/notte | ora=%s | current_display=%s | azione=forza_ON",
            now_hour,
            current_bms_display,
        )

        if current_bms_display != "ON":
            remote_data = client.set_bms_communication(
                device_id=device_id,
                value="2",  # ON
            )

            logger.info(
                "[TASK] BMS forzato ON sera/notte OK | response=%s",
                remote_data,
            )
        else:
            logger.info("[TASK] BMS già ON sera/notte")

        return

    # 1) Lettura dati batteria
    if data is None:
        data = client.get_device_state_latest(
            device_id=device_id,
            data_source=data_source,
            save_to_db=False,
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
        "[TASK] battery_voltage=%s | raw_battery_voltage=%s",
        battery_voltage,
        raw_battery_voltage,
    )

    if battery_voltage is None:
        logger.warning("[TASK] Battery voltage non trovata o non convertibile")
        return

    # 2) Decide stato desiderato con isteresi
    desired_bms_value = None

    if battery_voltage > high_threshold:
        desired_bms_value = "1"   # OFF
    elif battery_voltage < low_threshold:
        desired_bms_value = "2"   # ON

    if desired_bms_value is None:
        logger.info(
            "[TASK] BMS nessuna azione | battery_voltage=%s | fascia neutra [%s - %s]",
            battery_voltage,
            low_threshold,
            high_threshold,
        )
        return

    # 3) Legge stato reale attuale dal portale
    status = client.get_bms_communication(device_id)
    status_data = status.get("data", {}) or {}
    current_bms_display = str(status_data.get("valueDisplay", "")).strip().upper()

    if current_bms_display == "OFF":
        current_bms_value = "1"
    elif current_bms_display == "ON":
        current_bms_value = "2"
    else:
        current_bms_value = None

    logger.info(
        "[TASK] BMS stato attuale | current_value=%s | current_display=%s | desired_value=%s",
        current_bms_value,
        current_bms_display,
        desired_bms_value,
    )

    # 4) Se già corretto non fare nulla
    if current_bms_value == desired_bms_value:
        logger.info(
            "[TASK] BMS già corretto | battery_voltage=%s | value=%s",
            battery_voltage,
            current_bms_value,
        )
        return

    # 5) Cambia stato
    logger.info(
        "[TASK] BMS cambio stato START | battery_voltage=%s | old_value=%s | new_value=%s",
        battery_voltage,
        current_bms_value,
        desired_bms_value,
    )

    remote_data = client.set_bms_communication(
        device_id=device_id,
        value=desired_bms_value,
    )

    logger.info(
        "[TASK] BMS cambio stato OK | battery_voltage=%s | new_value=%s | response=%s",
        battery_voltage,
        desired_bms_value,
        remote_data,
    )

def check_registered_devices_on_lan(logger):
    lan_check_url = os.getenv(
        "LAN_CHECK_URL",
        "http://host.docker.internal:5001/lan_check",
    )

    timeout_seconds = int(os.getenv("LAN_CHECK_TIMEOUT_SECONDS", "20"))
    max_attempts = int(os.getenv("LAN_CHECK_MAX_ATTEMPTS", "3"))
    retry_sleep_seconds = int(os.getenv("LAN_CHECK_RETRY_SLEEP_SECONDS", "30"))

    logger.info(
        "[TASK] check_registered_devices_on_lan START | url=%s | timeout=%s | attempts=%s | retry_sleep=%s",
        lan_check_url,
        timeout_seconds,
        max_attempts,
        retry_sleep_seconds,
    )

    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                "[TASK] LAN check attempt %s/%s | url=%s",
                attempt,
                max_attempts,
                lan_check_url,
            )

            r = requests.get(lan_check_url, timeout=timeout_seconds)
            r.raise_for_status()
            data = r.json()

            ok = data.get("ok")
            registered_count = data.get("registered_count")
            found_registered_count = data.get("found_registered_count")
            missing_count = data.get("missing_count")
            check_strategy = data.get("check_strategy")

            logger.info(
                "[TASK] LAN check result | ok=%s | strategy=%s | registered=%s | found=%s | missing=%s",
                ok,
                check_strategy,
                registered_count,
                found_registered_count,
                missing_count,
            )

            missing_devices = data.get("missing_devices", []) or []

            if missing_devices:
                for dev in missing_devices:
                    logger.warning(
                        "[TASK] LAN missing device | description=%s | mac=%s | type=%s | last_ip=%s",
                        dev.get("description"),
                        dev.get("macaddress"),
                        dev.get("device_type") or dev.get("configured_type"),
                        dev.get("last_ip"),
                    )
            else:
                logger.info("[TASK] LAN tutti i dispositivi registrati risultano online")

            return data

        except Exception as e:
            last_error = e
            logger.warning(
                "[TASK] LAN check failed | attempt=%s/%s | error=%s",
                attempt,
                max_attempts,
                e,
            )

            if attempt < max_attempts:
                logger.info(
                    "[TASK] LAN check retry tra %s secondi",
                    retry_sleep_seconds,
                )
                time.sleep(retry_sleep_seconds)

    logger.exception(
        "[TASK] check_registered_devices_on_lan ERROR definitivo dopo %s tentativi | error=%s",
        max_attempts,
        last_error,
    )

    return None


def acquire_and_save_host_status_data(logger):

    import os
    import re
    import json
    import time
    import sqlite3
    import subprocess

    from datetime import datetime

    db_path = os.getenv(
        "DB_PATH",
        "data/solar.db",
    )

    conn = None

    try:

        logger.info("")
        logger.info("##################################################################")
        logger.info("################### HOST STATUS SNAPSHOTS #######################")
        logger.info("##################################################################")

        ##################################################################
        # DB
        ##################################################################

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        cur = conn.cursor()

        ##################################################################
        # GET REAL HOST LAN IP
        ##################################################################

        logger.info(
            "[TASK] Host LAN IP acquisition START"
        )

        started = time.time()

        cmd = [

            "nsenter",

            "-t", "1",

            "-n",

            "ip",

            "route",

            "get",

            "8.8.8.8"

        ]

        result = subprocess.check_output(

            cmd,

            text=True,

        )

        #
        # Example:
        #
        # 8.8.8.8 via 192.168.1.1
        # dev enp1s0
        # src 192.168.1.155
        #

        match = re.search(

            r"src\s+(\d+\.\d+\.\d+\.\d+)",

            result

        )

        if not match:

            raise RuntimeError(
                "Impossibile determinare host LAN IP"
            )

        ip_status = match.group(1)

        elapsed = round(
            time.time() - started,
            2,
        )

        logger.info(
            "[TASK] Host LAN IP acquired | "
            "ip=%s | elapsed=%ss",
            ip_status,
            elapsed,
        )

        ##################################################################
        # INSERT SNAPSHOT
        ##################################################################

        cur.execute(
            '''
            INSERT INTO host_status_snapshots (

                created_at,

                device_id,

                ok,

                ip_status,

                raw_json

            )
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                datetime.now().isoformat(
                    timespec="seconds"
                ),

                4,

                1,

                ip_status,

                json.dumps({

                    "ip_status":
                        ip_status,

                    "source":
                        "nsenter ip route get 8.8.8.8",

                }),
            )
        )

        conn.commit()

        logger.info(
            "[TASK] Host snapshot saved OK | ip=%s",
            ip_status,
        )

        ##################################################################
        # END
        ##################################################################

        logger.info("")
        logger.info("##################################################################")
        logger.info("############### HOST STATUS COMPLETED ###########################")
        logger.info("##################################################################")

        conn.close()

        return True

    except Exception as e:

        logger.exception(
            "[TASK] acquire_and_save_host_status_data FAILED | "
            "error=%s",
            e,
        )

        try:

            if conn:
                conn.close()

        except:
            pass

        return False



def acquire_and_save_sensors_status_data(logger):

    import os
    import json
    import time
    import sqlite3
    import requests

    from datetime import datetime

    session = requests.Session()

    db_path = os.getenv(
        "DB_PATH",
        "data/solar.db",
    )

    conn = None

    try:

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        conn.row_factory = sqlite3.Row

        cur = conn.cursor()

        cur.execute(
            '''
            SELECT *
            FROM sensor_measurements_config
            WHERE enabled = 1
              AND call_type = 'status'
            ORDER BY device_id, id
            '''
        )

        configs = cur.fetchall()

        logger.info(
            "[TASK] status configs loaded | count=%s",
            len(configs),
        )

        for cfg in configs:

            config_id = cfg["id"]
            device_id = cfg["device_id"]
            endpoint_query = cfg["endpoint_query"]
            http_method = cfg["http_method"]
            description = cfg["description"]

            try:

                logger.info("")
                logger.info("############################################################")
                logger.info("################### STATUS REQUEST #########################")
                logger.info("############################################################")

                logger.info(
                    "[TASK] Status START | "
                    "config_id=%s | device_id=%s | desc=%s",
                    config_id,
                    device_id,
                    description,
                )

                url = (
                    f"http://host.docker.internal:5001/"
                    f"{device_id}/status"
                    f"?endpoint={endpoint_query}"
                )

                logger.info(
                    "[TASK] HTTP request START | "
                    "method=%s | url=%s",
                    http_method,
                    url,
                )

                started = time.time()

                r = session.get(
                    url,
                    timeout=(5, 20),
                )

                elapsed = round(
                    time.time() - started,
                    2,
                )

                logger.info(
                    "[TASK] HTTP request END | "
                    "status_code=%s | elapsed=%ss",
                    r.status_code,
                    elapsed,
                )

                r.raise_for_status()

                resp = r.json()

                if not resp.get("ok"):

                    logger.error(
                        "[TASK] status response NOT OK | "
                        "config_id=%s | resp=%s",
                        config_id,
                        resp,
                    )

                    continue

                logger.info(
                    "[TASK] Status response VALID | "
                    "config_id=%s",
                    config_id,
                )

                device_type = resp.get("device_type")

                response = (
                    resp.get("response")
                    or {}
                )

                ip_status = None
                wifi_ssid = None
                wifi_rssi = None
                uptime_s = None
                heap_free = None
                version = None

                #
                # ESP32
                #

                if device_type == "esp32":

                    ip_status = response.get("ip")

                    wifi_ssid = response.get("ssid")

                    wifi_rssi = response.get("rssi")

                    uptime_s = response.get("uptime_s")

                    heap_free = response.get("heap_free")

                    version = response.get("version")

                #
                # SHELLY
                #

                elif device_type == "shelly":

                    wifi_sta = (
                        response.get("wifi_sta")
                        or {}
                    )

                    ip_status = wifi_sta.get("ip")

                    wifi_ssid = wifi_sta.get("ssid")

                    wifi_rssi = wifi_sta.get("rssi")

                    uptime_s = response.get("uptime")

                    heap_free = response.get("ram_free")

                    version = (
                        response.get("update", {})
                        .get("old_version")
                    )

                #
                # BACKEND HOST
                #

                elif device_type == "backend_host":

                    ip_status = response.get("ip")

                    wifi_ssid = (
                        response.get("service_id")
                    )

                    wifi_rssi = None

                    uptime_s = None

                    heap_free = None

                    version = (
                        response.get("service")
                    )

                    logger.info(
                        "[TASK] backend_host detected | "
                        "ip=%s | service_id=%s",
                        ip_status,
                        wifi_ssid,
                    )

                #
                # UNKNOWN
                #

                else:

                    logger.error(
                        "[TASK] unsupported device type | "
                        "device_id=%s | type=%s",
                        device_id,
                        device_type,
                    )

                    continue

                cur.execute(
                    '''
                    INSERT INTO sensor_status_snapshots (

                        created_at,
                        device_id,
                        ok,

                        ip_status,
                        wifi_ssid,
                        wifi_rssi,

                        uptime_s,
                        heap_free,
                        version,

                        raw_json

                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        datetime.now().isoformat(
                            timespec="seconds"
                        ),

                        device_id,

                        1,

                        ip_status,
                        wifi_ssid,
                        wifi_rssi,

                        uptime_s,
                        heap_free,
                        version,

                        json.dumps(
                            resp,
                            ensure_ascii=False,
                        ),
                    )
                )

                logger.info(
                    "[TASK] Status snapshot saved OK | "
                    "config_id=%s",
                    config_id,
                )

                conn.commit()

            except Exception as e:

                logger.exception(
                    "[TASK] Status FAILED | "
                    "config_id=%s | device_id=%s | error=%s",
                    config_id,
                    device_id,
                    e,
                )

                continue

        logger.info("")
        logger.info("############################################################")
        logger.info("############# ALL STATUS COMPLETED #########################")
        logger.info("############################################################")

        session.close()

        conn.close()

        return True

    except Exception as e:

        logger.exception(
            "[TASK] acquire_and_save_sensors_status_data FAILED | error=%s",
            e,
        )

        try:

            if conn:
                conn.close()

        except:
            pass

        session.close()

        return False



def acquire_and_save_relays_status_data(logger):

    import os
    import json
    import sqlite3
    import requests

    from datetime import datetime

    session = requests.Session()

    db_path = os.getenv(
        "DB_PATH",
        "data/solar.db",
    )

    conn = None

    try:

        logger.info("")
        logger.info("##################################################################")
        logger.info("################### RELAYS STATUS SNAPSHOTS #####################")
        logger.info("##################################################################")

        ##################################################################
        # DB
        ##################################################################

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        conn.row_factory = sqlite3.Row

        cur = conn.cursor()

        ##################################################################
        # LOAD CONFIG
        ##################################################################

        cur.execute(
            '''
            SELECT *
            FROM sensor_measurements_config
            WHERE enabled = 1
              AND id = 13
            ORDER BY id
            '''
        )

        configs = [
            dict(row)
            for row in cur.fetchall()
        ]

        logger.info(
            "[TASK] Relay configs loaded | count=%s",
            len(configs),
        )

        ##################################################################
        # RELAY STATE SUMMARY
        ##################################################################

        relay_state_summary = {}

        ##################################################################
        # LOOP CONFIGS
        ##################################################################

        for cfg in configs:

            config_id = cfg.get("id")

            device_id = cfg.get("device_id")

            endpoint_query = cfg.get(
                "endpoint_query"
            )

            description = cfg.get(
                "description"
            )

            http_method = (
                cfg.get("http_method")
                or "GET"
            ).upper()

            call_type = (
                cfg.get("call_type")
                or "relay_state"
            )

            ##################################################################
            # REQUEST
            ##################################################################

            logger.info("")
            logger.info("############################################################")
            logger.info("################## RELAY REQUEST ###########################")
            logger.info("############################################################")

            logger.info(
                "[TASK] Relay request START | "
                "config_id=%s | "
                "device_id=%s | "
                "description=%s",
                config_id,
                device_id,
                description,
            )

            try:

                ##################################################################
                # URL
                ##################################################################

                url = (
                    f"http://host.docker.internal:5001/"
                    f"{device_id}/{call_type}"
                    f"?endpoint={endpoint_query}"
                )

                logger.info(
                    "[TASK] HTTP request START | "
                    "method=%s | "
                    "url=%s",
                    http_method,
                    url,
                )

                ##################################################################
                # HTTP CALL
                ##################################################################

                if http_method == "GET":

                    r = session.get(
                        url,
                        timeout=(5, 20),
                    )

                else:

                    logger.error(
                        "[TASK] Unsupported HTTP method | "
                        "config_id=%s | "
                        "method=%s",
                        config_id,
                        http_method,
                    )

                    continue

                logger.info(
                    "[TASK] HTTP request END | "
                    "status_code=%s",
                    r.status_code,
                )

                r.raise_for_status()

                resp = r.json()

                ##################################################################
                # VALIDATE RESPONSE
                ##################################################################

                if not resp.get("ok"):

                    logger.warning(
                        "[TASK] Relay response NOT OK | "
                        "config_id=%s | "
                        "device_id=%s",
                        config_id,
                        device_id,
                    )

                    continue

                response = (
                    resp.get("response")
                    or []
                )

                if not isinstance(response, list):

                    logger.warning(
                        "[TASK] Relay response invalid | "
                        "config_id=%s | "
                        "device_id=%s",
                        config_id,
                        device_id,
                    )

                    continue

                ##################################################################
                # SAVE RELAYS
                ##################################################################

                relay_saved_count = 0

                for relay in response:

                    try:

                        relay_id = relay.get("id")

                        is_on = relay.get("is_on")

                        real_state = relay.get(
                            "real_state"
                        )

                        feedback_invert = relay.get(
                            "feedback_invert"
                        )

                        feedback_pin = relay.get(
                            "feedback_pin"
                        )

                        relay_pin = relay.get(
                            "pin"
                        )

                        ##################################################################
                        # BOOL -> INT
                        ##################################################################

                        if is_on is not None:
                            is_on = int(bool(is_on))

                        if real_state is not None:
                            real_state = int(
                                bool(real_state)
                            )

                        if feedback_invert is not None:
                            feedback_invert = int(
                                bool(feedback_invert)
                            )

                        ##################################################################
                        # SAVE SUMMARY
                        ##################################################################

                        relay_key_prefix = (
                            f"device_{device_id}_{relay_id}"
                        )

                        relay_state_summary[
                            f"{relay_key_prefix}_is_on"
                        ] = is_on

                        relay_state_summary[
                            f"{relay_key_prefix}_real_state"
                        ] = real_state

                        #
                        # Shortcut relay1
                        #

                        if relay_id == "relay1":

                            relay_state_summary[
                                "relay1_real_state"
                            ] = real_state

                            relay_state_summary[
                                "relay1_is_on"
                            ] = is_on

                        ##################################################################
                        # DB INSERT
                        ##################################################################

                        cur.execute(
                            '''
                            INSERT INTO
                            relay_status_snapshots (

                                created_at,

                                device_id,

                                relay_id,

                                is_on,

                                real_state,

                                feedback_invert,

                                feedback_pin,

                                relay_pin,

                                raw_json

                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''',
                            (
                                datetime.now().isoformat(
                                    timespec="seconds"
                                ),

                                device_id,

                                relay_id,

                                is_on,

                                real_state,

                                feedback_invert,

                                feedback_pin,

                                relay_pin,

                                json.dumps(
                                    relay,
                                    ensure_ascii=False,
                                ),
                            )
                        )

                        relay_saved_count += 1

                        logger.info(
                            "[TASK] Relay snapshot prepared | "
                            "device_id=%s | "
                            "relay_id=%s | "
                            "is_on=%s | "
                            "real_state=%s",
                            device_id,
                            relay_id,
                            is_on,
                            real_state,
                        )

                    except Exception as e:

                        logger.exception(
                            "[TASK] Relay save FAILED | "
                            "device_id=%s | "
                            "relay=%s | "
                            "error=%s",
                            device_id,
                            relay,
                            e,
                        )

                conn.commit()

                logger.info(
                    "[TASK] Relay snapshot saved | "
                    "config_id=%s | "
                    "device_id=%s | "
                    "count=%s",
                    config_id,
                    device_id,
                    relay_saved_count,
                )

            except Exception as e:

                logger.exception(
                    "[TASK] Relay acquisition FAILED | "
                    "config_id=%s | "
                    "device_id=%s | "
                    "error=%s",
                    config_id,
                    device_id,
                    e,
                )

        ##################################################################
        # END
        ##################################################################

        logger.info("")
        logger.info("##################################################################")
        logger.info("############ RELAYS STATUS COMPLETED ############################")
        logger.info("##################################################################")

        logger.info(
            "[TASK] Relay summary | %s",
            relay_state_summary,
        )

        session.close()

        conn.close()

        return {
            "ok": True,
            "relay_state_summary": relay_state_summary,
        }

    except Exception as e:

        logger.exception(
            "[TASK] acquire_and_save_relays_status_data FAILED | "
            "error=%s",
            e,
        )

        try:

            if conn:
                conn.close()

        except:
            pass

        session.close()

        return {
            "ok": False,
            "relay_state_summary": {},
        }


def acquire_and_save_sensors_measurements_data(logger):

    import os
    import json
    import time
    import sqlite3
    import requests

    from datetime import datetime

    session = requests.Session()

    ##################################################################
    # HELPERS
    ##################################################################

    def assign_if_not_none(current_value, new_value):

        """
        Mantiene current_value solo se new_value è None.
        Permette invece 0 / 0.0 / False.
        """

        return (
            new_value
            if new_value is not None
            else current_value
        )

    def normalize_float(
        value,
        *,
        min_value=None,
        max_value=None,
    ):

        """
        Converte in float e valida range.

        Restituisce:
            - float valido
            - None se invalido
        """

        if value is None:
            return None

        try:

            value = float(value)

        except Exception:

            return None

        #
        # Range validation
        #

        if (
            min_value is not None
            and value < min_value
        ):
            return None

        if (
            max_value is not None
            and value > max_value
        ):
            return None

        return value

    db_path = os.getenv(
        "DB_PATH",
        "data/solar.db",
    )

    #
    # CONFIGURABLE COOLDOWNS
    #

    same_device_sleep = float(
        os.getenv(
            "MEASUREMENT_SAME_DEVICE_SLEEP_SECONDS",
            "2",
        )
    )

    different_device_sleep = float(
        os.getenv(
            "MEASUREMENT_DIFFERENT_DEVICE_SLEEP_SECONDS",
            "0.5",
        )
    )

    connect_timeout = int(
        os.getenv(
            "MEASUREMENT_CONNECT_TIMEOUT_SECONDS",
            "5",
        )
    )

    read_timeout = int(
        os.getenv(
            "MEASUREMENT_READ_TIMEOUT_SECONDS",
            "40",
        )
    )

    conn = None

    try:

        ##################################################################
        # LOAD CONFIG
        ##################################################################

        logger.info("")
        logger.info("##################################################################")
        logger.info("################ LOAD MEASUREMENTS CONFIG #######################")
        logger.info("##################################################################")

        logger.info(
            "[TASK] Loading sensor measurements config"
        )

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        conn.row_factory = sqlite3.Row

        cur = conn.cursor()

        cur.execute(
            '''
            SELECT *
            FROM sensor_measurements_config
            WHERE enabled = 1
              AND call_type = 'measurment'
            ORDER BY device_id, id
            '''
        )

        configs = [
            dict(row)
            for row in cur.fetchall()
        ]

        logger.info(
            "[TASK] Loaded measurement configs | count=%s",
            len(configs),
        )

        ##################################################################
        # EXECUTE MEASUREMENTS
        ##################################################################

        previous_device_id = None

        for cfg in configs:

            config_id = cfg.get("id")

            device_id = cfg.get("device_id")

            endpoint_query = cfg.get(
                "endpoint_query"
            )

            description = cfg.get(
                "description"
            )

            http_method = (
                cfg.get("http_method")
                or "GET"
            ).upper()

            call_type = cfg.get(
                "call_type"
            )

            ##################################################################
            # DEVICE COOLDOWN
            ##################################################################

            if previous_device_id == device_id:

                logger.info("")
                logger.info("############################################################")
                logger.info("############ SAME DEVICE COOLDOWN ##########################")
                logger.info("############################################################")

                logger.info(
                    "[TASK] Cooldown START | "
                    "same device | "
                    "device_id=%s | "
                    "sleep=%ss",
                    device_id,
                    same_device_sleep,
                )

                time.sleep(
                    same_device_sleep
                )

                logger.info(
                    "[TASK] Cooldown END | "
                    "same device | "
                    "device_id=%s",
                    device_id,
                )

            else:

                logger.info("")
                logger.info("############################################################")
                logger.info("########### DIFFERENT DEVICE COOLDOWN ######################")
                logger.info("############################################################")

                logger.info(
                    "[TASK] Cooldown START | "
                    "device switch | "
                    "device_id=%s | "
                    "sleep=%ss",
                    device_id,
                    different_device_sleep,
                )

                time.sleep(
                    different_device_sleep
                )

                logger.info(
                    "[TASK] Cooldown END | "
                    "device switch | "
                    "device_id=%s",
                    device_id,
                )

            previous_device_id = device_id

            ##################################################################
            # START REQUEST
            ##################################################################

            logger.info("")
            logger.info("############################################################")
            logger.info("################# MEASUREMENT REQUEST ######################")
            logger.info("############################################################")

            logger.info(
                "[TASK] Measurement START | "
                "config_id=%s | "
                "device_id=%s | "
                "description=%s | "
                "call_type=%s",
                config_id,
                device_id,
                description,
                call_type,
            )

            try:

                ##################################################################
                # URL
                ##################################################################

                url = (
                    f"http://host.docker.internal:5001/"
                    f"{device_id}/{call_type}"
                    f"?endpoint={endpoint_query}"
                )

                logger.info(
                    "[TASK] HTTP request START | "
                    "method=%s | "
                    "url=%s | "
                    "connect_timeout=%s | "
                    "read_timeout=%s",
                    http_method,
                    url,
                    connect_timeout,
                    read_timeout,
                )

                started = time.time()

                ##################################################################
                # HTTP CALL
                ##################################################################

                if http_method == "GET":

                    r = session.get(
                        url,
                        timeout=(
                            connect_timeout,
                            read_timeout,
                        ),
                    )

                else:

                    logger.error(
                        "[TASK] Unsupported HTTP method | "
                        "config_id=%s | "
                        "method=%s",
                        config_id,
                        http_method,
                    )

                    continue

                elapsed = round(
                    time.time() - started,
                    2,
                )

                logger.info(
                    "[TASK] HTTP request END | "
                    "status_code=%s | "
                    "elapsed=%ss",
                    r.status_code,
                    elapsed,
                )

                r.raise_for_status()

                resp = r.json()

                ##################################################################
                # VALIDATE RESPONSE
                ##################################################################

                if not resp.get("ok"):

                    logger.error(
                        "[TASK] Measurement NOT OK | "
                        "config_id=%s | "
                        "response=%s",
                        config_id,
                        resp,
                    )

                    continue

                logger.info(
                    "[TASK] Measurement response VALID | "
                    "config_id=%s",
                    config_id,
                )

                response = (
                    resp.get("response")
                    or {}
                )

                ##################################################################
                # NORMALIZATION
                ##################################################################

                voltage = None
                current = None
                power = None
                power_factor = None
                energy = None
                frequency = None
                apparent_power = None
                total_power = None

                #
                # Shelly emeter/*
                #

                if isinstance(response, dict):

                    voltage = assign_if_not_none(
                        voltage,
                        response.get("voltage"),
                    )

                    current = assign_if_not_none(
                        current,
                        response.get("current"),
                    )

                    power = assign_if_not_none(
                        power,
                        response.get("power"),
                    )

                    power_factor = assign_if_not_none(
                        power_factor,
                        response.get("pf"),
                    )

                    energy = assign_if_not_none(
                        energy,
                        response.get("total"),
                    )

                    frequency = assign_if_not_none(
                        frequency,
                        response.get("frequency"),
                    )

                    total_power = assign_if_not_none(
                        total_power,
                        response.get("total_power"),
                    )

                #
                # ESP32 power_sensor
                #

                data = (
                    response.get("data")
                    if isinstance(response, dict)
                    else None
                )

                if isinstance(data, dict):

                    voltage = assign_if_not_none(
                        voltage,
                        data.get("voltage"),
                    )

                    current = assign_if_not_none(
                        current,
                        data.get("current"),
                    )

                    power = assign_if_not_none(
                        power,
                        data.get("power"),
                    )

                    power_factor = assign_if_not_none(
                        power_factor,
                        data.get("power_factor"),
                    )

                    energy = assign_if_not_none(
                        energy,
                        data.get("energy"),
                    )

                    frequency = assign_if_not_none(
                        frequency,
                        data.get("frequency"),
                    )

                #
                # ESP32 power
                #

                if isinstance(response, dict):

                    voltage = assign_if_not_none(
                        voltage,
                        response.get("volts_rms"),
                    )

                    current = assign_if_not_none(
                        current,
                        response.get("amps_rms"),
                    )

                    power = assign_if_not_none(
                        power,
                        response.get("power_w"),
                    )

                    power_factor = assign_if_not_none(
                        power_factor,
                        response.get("power_factor"),
                    )

                    apparent_power = assign_if_not_none(
                        apparent_power,
                        response.get(
                            "apparent_power_va"
                        ),
                    )

                ##################################################################
                # SANITY NORMALIZATION
                ##################################################################

                voltage = normalize_float(
                    voltage,
                    min_value=100,
                    max_value=300,
                )

                current = normalize_float(
                    current,
                    min_value=0,
                    max_value=200,
                )

                power = normalize_float(
                    power,
                    min_value=-50000,
                    max_value=50000,
                )

                power_factor = normalize_float(
                    power_factor,
                    min_value=-1.2,
                    max_value=1.2,
                )

                frequency = normalize_float(
                    frequency,
                    min_value=40,
                    max_value=70,
                )

                apparent_power = normalize_float(
                    apparent_power,
                    min_value=0,
                    max_value=50000,
                )

                total_power = normalize_float(
                    total_power,
                    min_value=-50000,
                    max_value=50000,
                )

                logger.info(
                    "[TASK] Normalization END | "
                    "power=%s | "
                    "voltage=%s | "
                    "current=%s | "
                    "pf=%s",
                    power,
                    voltage,
                    current,
                    power_factor,
                )

                ##################################################################
                # SAVE SNAPSHOT
                ##################################################################

                cur.execute(
                    '''
                    INSERT INTO
                    sensor_measurement_snapshots (

                        created_at,

                        device_id,

                        measurement_config_id,

                        ok,

                        voltage,

                        current,

                        power,

                        power_factor,

                        energy,

                        frequency,

                        apparent_power,

                        total_power,

                        raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        datetime.now().isoformat(
                            timespec="seconds"
                        ),

                        device_id,

                        config_id,

                        1,

                        voltage,

                        current,

                        power,

                        power_factor,

                        energy,

                        frequency,

                        apparent_power,

                        total_power,

                        json.dumps(
                            resp,
                            ensure_ascii=False,
                        ),
                    )
                )

                conn.commit()

                logger.info(
                    "[TASK] Snapshot saved OK | "
                    "config_id=%s",
                    config_id,
                )

            except Exception as e:

                logger.exception(
                    "[TASK] Measurement FAILED | "
                    "config_id=%s | "
                    "device_id=%s | "
                    "description=%s | "
                    "error=%s",
                    config_id,
                    device_id,
                    description,
                    e,
                )

                continue

        ##################################################################
        # END
        ##################################################################

        logger.info("")
        logger.info("##################################################################")
        logger.info("############ ALL MEASUREMENTS COMPLETED #########################")
        logger.info("##################################################################")

        session.close()

        conn.close()

        return True

    except Exception as e:

        logger.exception(
            "[TASK] acquire_and_save_sensors_measurements_data FAILED | "
            "error=%s",
            e,
        )

        try:

            if conn:
                conn.close()

        except:
            pass

        session.close()

        return False


def check_and_refresh_tesla_token(logger):
    """
    Task: controlla il token Tesla salvato in data/tesla_token.json.
    Se manca meno di 1 ora alla scadenza, esegue refresh_tesla_token().
    """

    token_path = Path(os.getenv("TESLA_TOKEN_PATH", "data/tesla_token.json"))
    refresh_before_seconds = int(os.getenv("TESLA_REFRESH_BEFORE_SECONDS", "3600"))

    logger.info(
        "[TASK] check_and_refresh_tesla_token START | token_path=%s | refresh_before_seconds=%s",
        token_path,
        refresh_before_seconds,
    )

    try:
        if not token_path.exists():
            logger.warning("[TASK] Tesla token file non trovato | path=%s", token_path)
            return None

        with token_path.open("r", encoding="utf-8") as f:
            token_data = json.load(f)

        saved_at_raw = token_data.get("saved_at")
        expires_in = int(token_data.get("expires_in") or 0)

        if not saved_at_raw or not expires_in:
            logger.warning(
                "[TASK] Tesla token incompleto | saved_at=%s | expires_in=%s",
                saved_at_raw,
                expires_in,
            )
            return None

        saved_at = datetime.strptime(saved_at_raw, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        expires_at = saved_at.timestamp() + expires_in
        seconds_left = int(expires_at - now.timestamp())

        logger.info(
            "[TASK] Tesla token status | saved_at=%s | expires_in=%s | seconds_left=%s | minutes_left=%.1f",
            saved_at_raw,
            expires_in,
            seconds_left,
            seconds_left / 60,
        )

        if seconds_left > refresh_before_seconds:
            logger.info(
                "[TASK] Tesla token ancora valido | seconds_left=%s | nessun refresh",
                seconds_left,
            )
            return {
                "ok": True,
                "refreshed": False,
                "seconds_left": seconds_left,
            }

        logger.warning(
            "[TASK] Tesla token vicino alla scadenza | seconds_left=%s | refresh START",
            seconds_left,
        )

        refreshed_data = refresh_tesla_token()

        logger.info(
            "[TASK] Tesla token refresh OK | has_access_token=%s | has_refresh_token=%s | expires_in=%s | saved_at=%s",
            bool(refreshed_data.get("access_token")),
            bool(refreshed_data.get("refresh_token")),
            refreshed_data.get("expires_in"),
            refreshed_data.get("saved_at"),
        )

        return {
            "ok": True,
            "refreshed": True,
            "seconds_left_before_refresh": seconds_left,
            "data": refreshed_data,
        }

    except Exception as e:
        logger.exception("[TASK] check_and_refresh_tesla_token ERROR | error=%s", e)
        return None