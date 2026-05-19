"""
db.py

Modulo dedicato al database SQLite.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_DB_PATH = "data/solar.db"
DEFAULT_LAN_SCANNER_DB_PATH = "/app/lan_scanner_data/lan_scanner.db"


def _build_sqlite_url(db_path: str) -> str:
    return f"sqlite:///{Path(db_path).as_posix()}"


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    _build_sqlite_url(os.getenv("DB_PATH", DEFAULT_DB_PATH)),
)
LAN_SCANNER_DATABASE_URL = os.getenv(
    "LAN_SCANNER_DATABASE_URL",
    _build_sqlite_url(os.getenv("LAN_SCANNER_DB_PATH", DEFAULT_LAN_SCANNER_DB_PATH)),
)
INIT_SQL_PATH = Path("init.sql")


MAX_AUTH_TOKENS = int(os.getenv("MAX_AUTH_TOKENS", "100"))
MAX_USER_INFO_SNAPSHOTS = int(os.getenv("MAX_USER_INFO_SNAPSHOTS", "100"))
MAX_DEVICE_SNAPSHOTS = int(os.getenv("MAX_DEVICE_SNAPSHOTS", "20000"))
MAX_DEVICE_SNAPSHOTS_FLAT = int(os.getenv("MAX_DEVICE_SNAPSHOTS_FLAT", "20000"))


def now_rome_str() -> str:
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M:%S")


def _sqlite_target_from_url(database_url: str) -> str:
    sqlite_prefix = "sqlite:///"

    if not database_url.startswith(sqlite_prefix):
        raise ValueError(
            "Sono supportate solo DATABASE_URL SQLite, ad esempio sqlite:///data/solar.db"
        )

    return database_url[len(sqlite_prefix):]


def _get_sqlite_connection(database_url: str, timeout: float = 5.0):
    db_target = _sqlite_target_from_url(database_url)

    if db_target != ":memory:":
        Path(db_target).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_target, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn


def get_connection(timeout: float = 5.0):
    return _get_sqlite_connection(DATABASE_URL, timeout=timeout)


def get_lan_scanner_connection(timeout: float = 5.0):
    return _get_sqlite_connection(LAN_SCANNER_DATABASE_URL, timeout=timeout)


def get_sensor_measurement_config(config_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                device_id,
                call_type,
                http_method,
                endpoint_query,
                payload,
                response_structure,
                description,
                enabled,
                port
            FROM sensor_measurements_config
            WHERE id = ?
            """,
            (config_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_sensor_measurement_configs(
    *,
    enabled_only: bool = True,
    device_id: str | None = None,
    call_type: str | None = None,
    config_ids: list[int] | None = None,
):
    query_lines = [
        "SELECT *",
        "FROM sensor_measurements_config",
    ]
    conditions = []
    params = []

    if enabled_only:
        conditions.append("enabled = 1")

    if device_id is not None:
        conditions.append("device_id = ?")
        params.append(device_id)

    if call_type is not None:
        conditions.append("call_type = ?")
        params.append(call_type)

    if config_ids is not None:
        if not config_ids:
            return []

        placeholders = ",".join(["?"] * len(config_ids))
        conditions.append(f"id IN ({placeholders})")
        params.extend(config_ids)

    if conditions:
        query_lines.append("WHERE " + " AND ".join(conditions))

    order_by = "ORDER BY id" if device_id is not None else "ORDER BY device_id, id"
    query_lines.append(order_by)
    query = "\n".join(query_lines)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_lan_scanner_device_last_ip(device_id):
    conn = get_lan_scanner_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT last_ip
            FROM device
            WHERE id = ?
            """,
            (device_id,),
        )
        row = cur.fetchone()
        return row["last_ip"] if row else None
    finally:
        conn.close()


def insert_host_status_snapshot(
    created_at: str,
    device_id,
    ok,
    ip_status: str | None,
    raw_json: str,
) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO host_status_snapshots (
                created_at,
                device_id,
                ok,
                ip_status,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (created_at, device_id, ok, ip_status, raw_json),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_sensor_status_snapshot(
    created_at: str,
    device_id,
    ok,
    ip_status: str | None,
    wifi_ssid: str | None,
    wifi_rssi,
    uptime_s,
    heap_free,
    version: str | None,
    raw_json: str,
) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
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
            """,
            (
                created_at,
                device_id,
                ok,
                ip_status,
                wifi_ssid,
                wifi_rssi,
                uptime_s,
                heap_free,
                version,
                raw_json,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_relay_status_snapshot(
    created_at: str,
    device_id,
    relay_id: str | None,
    is_on,
    real_state,
    feedback_invert,
    feedback_pin,
    relay_pin,
    raw_json: str,
) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO relay_status_snapshots (
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
            """,
            (
                created_at,
                device_id,
                relay_id,
                is_on,
                real_state,
                feedback_invert,
                feedback_pin,
                relay_pin,
                raw_json,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_sensor_measurement_snapshot(
    created_at: str,
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
    raw_json: str,
) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sensor_measurement_snapshots (
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
            """,
            (
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
                raw_json,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def init_db():
    conn = get_connection()
    try:
        with open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def cleanup_table_keep_latest(table_name: str, max_rows: int, order_column: str = "id") -> None:
    allowed_tables = {
        "auth_tokens",
        "user_info_snapshots",
        "device_snapshots",
        "device_snapshots_flat",
    }

    if table_name not in allowed_tables:
        raise ValueError(f"Tabella non consentita: {table_name}")

    if max_rows <= 0:
        return

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            DELETE FROM {table_name}
            WHERE {order_column} NOT IN (
                SELECT {order_column}
                FROM {table_name}
                ORDER BY {order_column} DESC
                LIMIT ?
            )
        """, (max_rows,))
        conn.commit()
    finally:
        conn.close()


def insert_token(token: str, login_payload_json: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO auth_tokens (created_at, token, login_payload_json)
            VALUES (?, ?, ?)
        """, (now_rome_str(), token, login_payload_json))
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()

    cleanup_table_keep_latest("auth_tokens", MAX_AUTH_TOKENS)
    return row_id


def insert_user_info(token: str, payload_json: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_info_snapshots (created_at, token, payload_json)
            VALUES (?, ?, ?)
        """, (now_rome_str(), token, payload_json))
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()

    cleanup_table_keep_latest("user_info_snapshots", MAX_USER_INFO_SNAPSHOTS)
    return row_id


def get_last_token_row():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, created_at, token, login_payload_json
            FROM auth_tokens
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_last_user_info_row():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, created_at, token, payload_json
            FROM user_info_snapshots
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_last_token_value():
    row = get_last_token_row()
    if not row:
        return None
    return row["token"]


def insert_device_snapshot(device_row_key: str, update_time: str, json_data: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_snapshots (created_at, device_row_key, update_time, json_data)
            VALUES (?, ?, ?, ?)
        """, (now_rome_str(), device_row_key, update_time, json_data))
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()

    cleanup_table_keep_latest("device_snapshots", MAX_DEVICE_SNAPSHOTS)
    return row_id


def insert_device_snapshot_flat(
    device_row_key: str,
    update_time: str | None,
    inverter_program_version: str | None,
    internal_model: str | None,
    input_voltage: str | None,
    input_frequency: str | None,
    output_voltage: str | None,
    output_frequency: str | None,
    battery_voltage: str | None,
    battery_capacity: str | None,
    inverter_charging_current: str | None,
    load_percentage: str | None,
    device_temp: str | None,
    machine_status_code: str | None,
    system_run_time: str | None,
    system_operation_status: str | None,
    battery_number_in_series: str | None,
    controller_program_version: str | None,
    pv_voltage: str | None,
    controller_charging_current: str | None,
    controller_temp: str | None,
    controller_status_code: str | None,
    controller_connection_status: str | None,
    controller_charging_status: str | None,
    inverter_charge_status: str | None,
    battery_voltage_is_full: str | None,
    controller_malfunction_alarm: str | None,
    controller_warning_alarm: str | None,
    inverter_fault_alarm: str | None,
    inverter_warning_alarm: str | None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_snapshots_flat (
                created_at,
                device_row_key,
                update_time,
                inverter_program_version,
                internal_model,
                input_voltage,
                input_frequency,
                output_voltage,
                output_frequency,
                battery_voltage,
                battery_capacity,
                inverter_charging_current,
                load_percentage,
                device_temp,
                machine_status_code,
                system_run_time,
                system_operation_status,
                battery_number_in_series,
                controller_program_version,
                pv_voltage,
                controller_charging_current,
                controller_temp,
                controller_status_code,
                controller_connection_status,
                controller_charging_status,
                inverter_charge_status,
                battery_voltage_is_full,
                controller_malfunction_alarm,
                controller_warning_alarm,
                inverter_fault_alarm,
                inverter_warning_alarm
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_rome_str(),
            device_row_key,
            update_time,
            inverter_program_version,
            internal_model,
            input_voltage,
            input_frequency,
            output_voltage,
            output_frequency,
            battery_voltage,
            battery_capacity,
            inverter_charging_current,
            load_percentage,
            device_temp,
            machine_status_code,
            system_run_time,
            system_operation_status,
            battery_number_in_series,
            controller_program_version,
            pv_voltage,
            controller_charging_current,
            controller_temp,
            controller_status_code,
            controller_connection_status,
            controller_charging_status,
            inverter_charge_status,
            battery_voltage_is_full,
            controller_malfunction_alarm,
            controller_warning_alarm,
            inverter_fault_alarm,
            inverter_warning_alarm,
        ))
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()

    cleanup_table_keep_latest("device_snapshots_flat", MAX_DEVICE_SNAPSHOTS_FLAT)
    return row_id


def get_device_metric_history(
    device_row_key: str,
    metric_name: str,
    start_time: str,
    end_time: str,
):
    allowed_metrics = {
        "battery_voltage",
        "battery_capacity",
        "inverter_charging_current",
        "controller_charging_current",
        "load_percentage",
        "device_temp",
        "pv_voltage",
    }

    if metric_name not in allowed_metrics:
        raise ValueError(f"Metrica non consentita: {metric_name}")

    conn = get_connection()
    try:
        cur = conn.cursor()
        query = f"""
            SELECT update_time, created_at, {metric_name} AS metric_value
            FROM device_snapshots_flat
            WHERE device_row_key = ?
              AND created_at >= ?
              AND created_at <= ?
            ORDER BY created_at ASC
        """
        cur.execute(query, (device_row_key, start_time, end_time))
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def insert_tesla_vehicle_snapshot(
    vin: str,
    state: str | None,
    battery_level,
    charging_state: str | None,
    charge_limit_soc,
    charger_power,
    inside_temp,
    outside_temp,
    locked,
    charge_port_door_open,
    charge_port_latch: str | None,
    charge_port_color: str | None,
    conn_charge_cable: str | None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tesla_vehicle_snapshots (
                created_at,
                vin,
                state,
                battery_level,
                charging_state,
                charge_limit_soc,
                charger_power,
                inside_temp,
                outside_temp,
                locked,
                charge_port_door_open,
                charge_port_latch,
                charge_port_color,
                conn_charge_cable
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_rome_str(),
            vin,
            state,
            battery_level,
            charging_state,
            charge_limit_soc,
            charger_power,
            inside_temp,
            outside_temp,
            1 if locked else 0 if locked is not None else None,
            1 if charge_port_door_open else 0 if charge_port_door_open is not None else None,
            charge_port_latch,
            charge_port_color,
            conn_charge_cable,
        ))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()