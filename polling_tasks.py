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


def acquire_and_save_sensors_data(logger, lan_result):
    """
    Task: acquisisce dati dai sensori LAN trovati da lan_scanner e li salva su SQLite.

    Sensori gestiti:
    - Produzione Fronius:
        http://IP/power_sensor?id=pz1

    - Shelly EM3 Assorbimenti da ENEL:
        http://IP/status
    """

    logger.info(
        "[TASK] acquire_and_save_sensors_data START | found_registered_count=%s | missing_count=%s",
        lan_result.get("found_registered_count"),
        lan_result.get("missing_count"),
    )

    db_path = Path(os.getenv("DB_PATH", "data/solar.db"))
    timeout_seconds = int(os.getenv("SENSORS_HTTP_TIMEOUT_SECONDS", "10"))

    found_devices = lan_result.get("found_registered_devices", []) or []

    if not found_devices:
        logger.warning(
            "[TASK] acquire_and_save_sensors_data SKIP | nessun dispositivo trovato"
        )
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()
        saved_count = 0

        for dev in found_devices:
            description = dev.get("description")
            ip = dev.get("ip")
            macaddress = dev.get("macaddress")
            configured_type = dev.get("configured_type")

            if not ip:
                logger.warning(
                    "[TASK] sensore SKIP | description=%s | motivo=ip mancante",
                    description,
                )
                continue

            # =========================================================
            # 1) Produzione Fronius / ESP32
            # =========================================================
            if description == "Produzione Fronius":
                channel_index = 1
                endpoint = f"http://{ip}/power_sensor?id=pz{channel_index}"

                logger.info(
                    "[TASK] Lettura sensore START | name=%s | endpoint=%s",
                    description,
                    endpoint,
                )

                try:
                    r = requests.get(endpoint, timeout=timeout_seconds)
                    r.raise_for_status()
                    payload = r.json()

                    data = payload.get("data", {}) or {}

                    cur.execute("""
                        INSERT INTO sensor_snapshots (
                            created_at,
                            sensor_name,
                            sensor_type,
                            ip,
                            macaddress,
                            endpoint,
                            channel_index,
                            ok,
                            voltage,
                            current,
                            power,
                            power_factor,
                            frequency,
                            energy,
                            total_power,
                            raw_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        datetime.now().isoformat(timespec="seconds"),
                        description,
                        configured_type,
                        ip,
                        macaddress,
                        endpoint,
                        channel_index,
                        1 if payload.get("ok") else 0,
                        data.get("voltage"),
                        data.get("current"),
                        data.get("power"),
                        data.get("power_factor"),
                        data.get("frequency"),
                        data.get("energy"),
                        None,
                        json.dumps(payload, ensure_ascii=False),
                    ))

                    saved_count += 1

                    logger.info(
                        "[TASK] Lettura sensore OK | name=%s | channel=%s | voltage=%s | current=%s | power=%s",
                        description,
                        channel_index,
                        data.get("voltage"),
                        data.get("current"),
                        data.get("power"),
                    )

                except Exception as e:
                    logger.exception(
                        "[TASK] Lettura sensore ERROR | name=%s | endpoint=%s | error=%s",
                        description,
                        endpoint,
                        e,
                    )

            # =========================================================
            # 2) Shelly EM3
            # =========================================================
            elif description == "Shelly EM3 Assorbimenti da ENEL":
                endpoint = f"http://{ip}/status"

                logger.info(
                    "[TASK] Lettura Shelly START | name=%s | endpoint=%s",
                    description,
                    endpoint,
                )

                try:
                    r = requests.get(endpoint, timeout=timeout_seconds)
                    r.raise_for_status()
                    payload = r.json()

                    emeters = payload.get("emeters", []) or []
                    total_power = payload.get("total_power")

                    for idx, em in enumerate(emeters):
                        channel_index = idx

                        cur.execute("""
                            INSERT INTO sensor_snapshots (
                                created_at,
                                sensor_name,
                                sensor_type,
                                ip,
                                macaddress,
                                endpoint,
                                channel_index,
                                ok,
                                voltage,
                                current,
                                power,
                                power_factor,
                                frequency,
                                energy,
                                total_power,
                                raw_json
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            datetime.now().isoformat(timespec="seconds"),
                            f"{description} L{idx + 1}",
                            configured_type,
                            ip,
                            macaddress,
                            endpoint,
                            channel_index,
                            1 if em.get("is_valid") else 0,
                            em.get("voltage"),
                            em.get("current"),
                            em.get("power"),
                            em.get("pf"),
                            None,
                            em.get("total"),
                            total_power,
                            json.dumps(payload, ensure_ascii=False),
                        ))

                        saved_count += 1

                    logger.info(
                        "[TASK] Lettura Shelly OK | name=%s | channels=%s | total_power=%s",
                        description,
                        len(emeters),
                        total_power,
                    )

                except Exception as e:
                    logger.exception(
                        "[TASK] Lettura Shelly ERROR | name=%s | endpoint=%s | error=%s",
                        description,
                        endpoint,
                        e,
                    )

            else:
                logger.info(
                    "[TASK] sensore ignorato | description=%s | ip=%s | type=%s",
                    description,
                    ip,
                    configured_type,
                )

        conn.commit()

        logger.info(
            "[TASK] acquire_and_save_sensors_data END | saved_count=%s",
            saved_count,
        )

        return {
            "ok": True,
            "saved_count": saved_count,
        }

    finally:
        conn.close()




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