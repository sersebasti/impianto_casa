import os
from datetime import datetime


def acquire_and_save_device_state(client, logger, device_id, data_source):
    """
    Task: acquisisce lo stato inverter/batteria e lo salva nel DB.
    Restituisce il dict dei dati ottenuti.
    """
    logger.info("[TASK] acquire_and_save_device_state | device_id=%s | data_source=%s", device_id, data_source)
    data = client.get_device_state_latest(
        device_id=device_id,
        data_source=data_source,
        save_to_db=True,
    )
    logger.info("[TASK] acquire_and_save_device_state OK")
    return data


from datetime import datetime
import os


def check_battery_and_bms(client, logger, device_id, data_source, interval_seconds, data=None):
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
        "[TASK] check_battery_and_bms | low_threshold=%s | high_threshold=%s | night_bms_on_hour=%s",
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
