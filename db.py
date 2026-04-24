"""
db.py

Modulo dedicato al database SQLite.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path("data/solar.db")
INIT_SQL_PATH = Path("init.sql")

MAX_AUTH_TOKENS = int(os.getenv("MAX_AUTH_TOKENS", "100"))
MAX_USER_INFO_SNAPSHOTS = int(os.getenv("MAX_USER_INFO_SNAPSHOTS", "100"))
MAX_DEVICE_SNAPSHOTS = int(os.getenv("MAX_DEVICE_SNAPSHOTS", "20000"))
MAX_DEVICE_SNAPSHOTS_FLAT = int(os.getenv("MAX_DEVICE_SNAPSHOTS_FLAT", "20000"))


def now_rome_str() -> str:
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M:%S")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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