"""
db.py

Modulo dedicato al database SQLite.

Cosa fa:
- apre la connessione a SQLite
- legge ed esegue lo schema da init.sql
- salva token e risposte login
- salva le risposte degli endpoint
- permette di leggere gli ultimi record salvati
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/solar.db")
INIT_SQL_PATH = Path("init.sql")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    with open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    conn.commit()
    conn.close()


def insert_token(token: str, login_payload_json: str) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO auth_tokens (token, login_payload_json)
        VALUES (?, ?)
    """, (token, login_payload_json))

    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def insert_user_info(token: str, payload_json: str) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO user_info_snapshots (token, payload_json)
        VALUES (?, ?)
    """, (token, payload_json))

    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_last_token_row():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, created_at, token, login_payload_json
        FROM auth_tokens
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_last_user_info_row():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, created_at, token, payload_json
        FROM user_info_snapshots
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


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
            INSERT INTO device_snapshots (device_row_key, update_time, json_data)
            VALUES (?, ?, ?)
        """, (device_row_key, update_time, json_data))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
            return cur.lastrowid
        finally:
            conn.close()