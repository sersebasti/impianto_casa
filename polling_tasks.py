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

    try:

        devices_url = (
            "http://host.docker.internal:5001/devices"
        )

        logger.info(
            "[TASK] devices request START | url=%s",
            devices_url,
        )

        r = session.get(
            devices_url,
            timeout=(3, 10),
        )

        r.raise_for_status()

        devices = r.json()

        logger.info(
            "[TASK] devices loaded OK | count=%s",
            len(devices),
        )

    except Exception as e:

        logger.exception(
            "[TASK] devices request FAILED | error=%s",
            e,
        )

        session.close()

        return False

    conn = None

    try:

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        cur = conn.cursor()

        for dev in devices:

            device_id = dev.get("id")
            device_description = dev.get("description")
            device_type = dev.get("device_type")

            try:

                url = (
                    f"http://host.docker.internal:5001/"
                    f"{device_id}/measurment"
                    f"?endpoint=status"
                )

                logger.info(
                    "[TASK] status request START | "
                    "device_id=%s | desc=%s | type=%s",
                    device_id,
                    device_description,
                    device_type,
                )

                started = time.time()

                r = session.get(
                    url,
                    timeout=(3, 10),
                )

                elapsed = round(
                    time.time() - started,
                    2,
                )

                r.raise_for_status()

                resp = r.json()

                logger.info(
                    "[TASK] status response OK | "
                    "device_id=%s | elapsed=%ss",
                    device_id,
                    elapsed,
                )

                if not resp.get("ok"):

                    logger.error(
                        "[TASK] status response NOT OK | "
                        "device_id=%s | resp=%s",
                        device_id,
                        resp,
                    )

                    session.close()

                    conn.close()

                    return False

                response = resp.get("response") or {}

                if device_type == "esp32":

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
                            response.get("ip"),
                            response.get("ssid"),
                            response.get("rssi"),
                            response.get("uptime_s"),
                            response.get("heap_free"),
                            response.get("version"),
                            json.dumps(
                                resp,
                                ensure_ascii=False,
                            ),
                        )
                    )

                elif device_type == "shelly":

                    wifi_sta = (
                        response.get("wifi_sta")
                        or {}
                    )

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
                            wifi_sta.get("ip"),
                            wifi_sta.get("ssid"),
                            wifi_sta.get("rssi"),
                            response.get("uptime"),
                            response.get("ram_free"),
                            (
                                response.get("update", {})
                                .get("old_version")
                            ),
                            json.dumps(
                                resp,
                                ensure_ascii=False,
                            ),
                        )
                    )

                else:

                    logger.error(
                        "[TASK] unsupported device type | "
                        "device_id=%s | type=%s",
                        device_id,
                        device_type,
                    )

                    session.close()

                    conn.close()

                    return False

                logger.info(
                    "[TASK] status snapshot saved | "
                    "device_id=%s",
                    device_id,
                )

            except Exception as e:

                logger.exception(
                    "[TASK] device FAILED | "
                    "device_id=%s | error=%s",
                    device_id,
                    e,
                )

                session.close()

                conn.close()

                return False

        conn.commit()

        logger.info(
            "[TASK] all status snapshots saved OK"
        )

        session.close()

        conn.close()

        return True

    except Exception as e:

        logger.exception(
            "[TASK] global acquire status FAILED | error=%s",
            e,
        )

        try:
            if conn:
                conn.close()
        except:
            pass

        session.close()

        return False


def acquire_and_save_sensors_measurements_data(logger):

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
                "description=%s",
                config_id,
                device_id,
                description,
            )

            try:

                url = (
                    f"http://host.docker.internal:5001/"
                    f"{device_id}/measurment"
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

                    session.close()

                    conn.close()

                    return False

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

                    session.close()

                    conn.close()

                    return False

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

                    voltage = (
                        response.get("voltage")
                        or voltage
                    )

                    current = (
                        response.get("current")
                        or current
                    )

                    power = (
                        response.get("power")
                        or power
                    )

                    power_factor = (
                        response.get("pf")
                        or power_factor
                    )

                    energy = (
                        response.get("total")
                        or energy
                    )

                    frequency = (
                        response.get("frequency")
                        or frequency
                    )

                    total_power = (
                        response.get("total_power")
                        or total_power
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

                    voltage = (
                        data.get("voltage")
                        or voltage
                    )

                    current = (
                        data.get("current")
                        or current
                    )

                    power = (
                        data.get("power")
                        or power
                    )

                    power_factor = (
                        data.get("power_factor")
                        or power_factor
                    )

                    energy = (
                        data.get("energy")
                        or energy
                    )

                    frequency = (
                        data.get("frequency")
                        or frequency
                    )

                #
                # ESP32 power
                #

                if isinstance(response, dict):

                    voltage = (
                        response.get("volts_rms")
                        or voltage
                    )

                    current = (
                        response.get("amps_rms")
                        or current
                    )

                    power = (
                        response.get("power_w")
                        or power
                    )

                    power_factor = (
                        response.get("power_factor")
                        or power_factor
                    )

                    apparent_power = (
                        response.get(
                            "apparent_power_va"
                        )
                        or apparent_power
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

                session.close()

                conn.close()

                return False

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