"""
db.py

Modulo dedicato all'accesso ai database relazionali del progetto.
"""

import os
import sqlite3
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, select
from sqlalchemy.orm import sessionmaker

from logger import get_logger
from models import AuthToken, SensorMeasurementsConfig, UserInfoSnapshot

DEFAULT_DB_PATH = "data/solar.db"
DEFAULT_LAN_SCANNER_DB_PATH = "/app/lan_scanner_data/lan_scanner.db"
DB_MODEL_READ_LOGS_ENABLED = os.getenv("LOG_DB_MODEL_READS", "0") == "1"
SQLITE_JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "WAL").upper()
SQLITE_SYNCHRONOUS = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL").upper()

logger = get_logger("db")


##########################################################################
######### DATABASE URLS ##################################################
##########################################################################


def _build_sqlite_url(db_path: str) -> str:
    return f"sqlite:///{Path(db_path).as_posix()}"


def build_database_url(*, dialect: str, db_path: str | None = None) -> str:
    if dialect != "sqlite":
        raise ValueError(f"Dialect non supportato per la build automatica: {dialect}")

    if not db_path:
        raise ValueError("db_path obbligatorio per costruire una DATABASE_URL SQLite")

    return _build_sqlite_url(db_path)


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    build_database_url(dialect="sqlite", db_path=os.getenv("DB_PATH", DEFAULT_DB_PATH)),
)
LAN_SCANNER_DATABASE_URL = os.getenv(
    "LAN_SCANNER_DATABASE_URL",
    build_database_url(
        dialect="sqlite",
        db_path=os.getenv("LAN_SCANNER_DB_PATH", DEFAULT_LAN_SCANNER_DB_PATH),
    ),
)


##########################################################################
######### SCHEMA / INIT ##################################################
##########################################################################


INIT_SQL_PATH = Path("init.sql")


##########################################################################
######### AUTH DOMAIN LIMITS #############################################
##########################################################################


AUTH_TOKEN_LIMIT = int(os.getenv("MAX_AUTH_TOKENS", "100"))
AUTH_USER_INFO_LIMIT = int(os.getenv("MAX_USER_INFO_SNAPSHOTS", "100"))


##########################################################################
######### DEVICE DOMAIN LIMITS ###########################################
##########################################################################


DEVICE_SNAPSHOT_LIMIT = int(os.getenv("MAX_DEVICE_SNAPSHOTS", "20000"))
DEVICE_SNAPSHOT_FLAT_LIMIT = int(os.getenv("MAX_DEVICE_SNAPSHOTS_FLAT", "20000"))


##########################################################################
######### GENERIC DB CORE ################################################
##########################################################################


def now_rome_str() -> str:
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M:%S")


def _get_database_dialect(database_url: str) -> str:
    parsed = urlparse(database_url)
    dialect = parsed.scheme.split("+", 1)[0].lower()

    if not dialect:
        raise ValueError(f"DATABASE_URL non valida: {database_url}")

    return dialect


def _translate_query_placeholders(query: str, dialect: str) -> str:
    if dialect in {"mysql", "mariadb"}:
        return query.replace("?", "%s")

    return query


class _CursorAdapter:
    def __init__(self, raw_cursor, dialect: str):
        self._raw_cursor = raw_cursor
        self._dialect = dialect

    @property
    def lastrowid(self):
        return self._raw_cursor.lastrowid

    def execute(self, query: str, params=None):
        translated_query = _translate_query_placeholders(query, self._dialect)

        if params is None:
            return self._raw_cursor.execute(translated_query)

        return self._raw_cursor.execute(translated_query, params)

    def fetchone(self):
        return self._raw_cursor.fetchone()

    def fetchall(self):
        return self._raw_cursor.fetchall()

    def __getattr__(self, attr):
        return getattr(self._raw_cursor, attr)


class _ConnectionAdapter:
    def __init__(self, raw_connection, dialect: str):
        self._raw_connection = raw_connection
        self._dialect = dialect

    def cursor(self):
        return _CursorAdapter(self._raw_connection.cursor(), self._dialect)

    def commit(self):
        return self._raw_connection.commit()

    def close(self):
        return self._raw_connection.close()

    def executescript(self, script: str):
        if self._dialect != "sqlite":
            raise NotImplementedError(
                "init_db con init.sql supporta solo SQLite. Per MySQL/MariaDB servono migrazioni dedicate."
            )

        return self._raw_connection.executescript(script)

    def __getattr__(self, attr):
        return getattr(self._raw_connection, attr)


def _sqlite_target_from_url(database_url: str) -> str:
    sqlite_prefix = "sqlite:///"

    if not database_url.startswith(sqlite_prefix):
        raise ValueError(
            "DATABASE_URL SQLite non valida, esempio atteso: sqlite:///data/solar.db"
        )

    return database_url[len(sqlite_prefix):]


def _connect_sqlite(database_url: str, timeout: float = 5.0):
    db_target = _sqlite_target_from_url(database_url)

    if db_target != ":memory:":
        Path(db_target).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_target, timeout=timeout)
    conn.row_factory = sqlite3.Row

    if db_target != ":memory:":
        conn.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE}")
        conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS}")

    conn.execute(f"PRAGMA busy_timeout={max(int(timeout * 1000), 1)}")
    return conn


def _connect_mysql(database_url: str, timeout: float = 5.0):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise RuntimeError(
            "Per usare MySQL/MariaDB serve PyMySQL installato nel runtime."
        ) from exc

    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")

    if not database_name:
        raise ValueError(f"Database name mancante nella DATABASE_URL: {database_url}")

    return pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=database_name,
        connect_timeout=max(int(timeout), 1),
        cursorclass=DictCursor,
        charset="utf8mb4",
        autocommit=False,
    )


def build_sqlite_database_url(db_path: str) -> str:
    return build_database_url(dialect="sqlite", db_path=db_path)


def get_database_dialect(database_url: str) -> str:
    return _get_database_dialect(database_url)


def _open_raw_connection(database_url: str, timeout: float = 5.0):
    dialect = _get_database_dialect(database_url)

    if dialect == "sqlite":
        return _connect_sqlite(database_url, timeout=timeout), dialect

    if dialect in {"mysql", "mariadb"}:
        return _connect_mysql(database_url, timeout=timeout), dialect

    raise ValueError(
        f"Dialect non supportato: {dialect}. Supportati: sqlite, mysql, mariadb"
    )


def _normalize_database_url_for_sqlalchemy(database_url: str) -> str:
    dialect = _get_database_dialect(database_url)

    if dialect == "mariadb":
        return database_url.replace("mariadb://", "mysql+pymysql://", 1)

    if dialect == "mysql" and "+" not in database_url.split("://", 1)[0]:
        return database_url.replace("mysql://", "mysql+pymysql://", 1)

    return database_url


@lru_cache(maxsize=4)
def _get_sqlalchemy_engine(database_url: str):
    normalized_url = _normalize_database_url_for_sqlalchemy(database_url)
    return create_engine(normalized_url)


@lru_cache(maxsize=4)
def _get_sqlalchemy_session_factory(database_url: str):
    return sessionmaker(bind=_get_sqlalchemy_engine(database_url))


def _model_to_dict(instance):
    return {
        attribute.key: getattr(instance, attribute.key)
        for attribute in sqlalchemy_inspect(instance).mapper.column_attrs
    }


def _log_model_read(
    helper_name: str,
    model_name: str,
    result_count: int,
    source: str | None = None,
):
    if not DB_MODEL_READ_LOGS_ENABLED:
        return

    message = "DB model read | helper=%s | model=%s | rows=%s"
    args = [helper_name, model_name, result_count]

    if source:
        message += " | source=%s"
        args.append(source)

    logger.info(message, *args)


def _fetch_one_model(
    statement,
    *,
    model_name: str,
    source: str | None = None,
    database_url: str = DATABASE_URL,
):
    session = _get_sqlalchemy_session_factory(database_url)()
    try:
        instance = session.execute(statement).scalars().first()
        _log_model_read(
            "_fetch_one_model",
            model_name,
            0 if instance is None else 1,
            source,
        )
        return _model_to_dict(instance) if instance else None
    finally:
        session.close()


def _fetch_all_models(
    statement,
    *,
    model_name: str,
    source: str | None = None,
    database_url: str = DATABASE_URL,
):
    session = _get_sqlalchemy_session_factory(database_url)()
    try:
        instances = session.execute(statement).scalars().all()
        _log_model_read("_fetch_all_models", model_name, len(instances), source)
        return [_model_to_dict(instance) for instance in instances]
    finally:
        session.close()


def get_connection_for_database_url(database_url: str, timeout: float = 5.0):
    raw_connection, dialect = _open_raw_connection(database_url, timeout=timeout)
    return _ConnectionAdapter(raw_connection, dialect)


def get_main_connection(timeout: float = 5.0):
    return get_connection_for_database_url(DATABASE_URL, timeout=timeout)


def get_lan_scanner_db_connection(timeout: float = 5.0):
    return get_connection_for_database_url(LAN_SCANNER_DATABASE_URL, timeout=timeout)


def get_connection(timeout: float = 5.0):
    return get_main_connection(timeout=timeout)


def get_lan_scanner_connection(timeout: float = 5.0):
    return get_lan_scanner_db_connection(timeout=timeout)


def _fetch_one(query: str, params=(), *, connection_factory=get_main_connection):
    conn = connection_factory()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _fetch_all(query: str, params=(), *, connection_factory=get_main_connection):
    conn = connection_factory()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _execute_write(
    query: str,
    params=(),
    *,
    connection_factory=get_main_connection,
    return_lastrowid: bool = False,
):
    conn = connection_factory()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        if return_lastrowid:
            return cur.lastrowid
        return None
    finally:
        conn.close()


##########################################################################
######### MAIN DATABASE ##################################################
##########################################################################


def get_sensor_measurement_config(config_id: int, source: str | None = None):
    return _fetch_one_model(
        select(SensorMeasurementsConfig).where(
            SensorMeasurementsConfig.id == config_id
        ),
        model_name="SensorMeasurementsConfig",
        source=source,
    )


def list_sensor_measurement_configs(
    *,
    enabled_only: bool = True,
    device_id: str | None = None,
    call_type: str | None = None,
    config_ids: list[int] | None = None,
    source: str | None = None,
):
    statement = select(SensorMeasurementsConfig)

    if enabled_only:
        statement = statement.where(SensorMeasurementsConfig.enabled == 1)

    if device_id is not None:
        statement = statement.where(SensorMeasurementsConfig.device_id == device_id)

    if call_type is not None:
        statement = statement.where(SensorMeasurementsConfig.call_type == call_type)

    if config_ids is not None:
        if not config_ids:
            return []

        statement = statement.where(SensorMeasurementsConfig.id.in_(config_ids))

    if device_id is not None:
        statement = statement.order_by(SensorMeasurementsConfig.id)
    else:
        statement = statement.order_by(
            SensorMeasurementsConfig.device_id,
            SensorMeasurementsConfig.id,
        )

    return _fetch_all_models(
        statement,
        model_name="SensorMeasurementsConfig",
        source=source,
    )


##########################################################################
######### LAN SCANNER DATABASE ###########################################
##########################################################################


def get_lan_scanner_device_last_ip(device_id):
    row = _fetch_one(
        """
        SELECT last_ip
        FROM device
        WHERE id = ?
        """,
        (device_id,),
        connection_factory=get_lan_scanner_db_connection,
    )
    if not row:
        return None
    return row["last_ip"]


##########################################################################
######### MAIN DATABASE WRITES ###########################################
##########################################################################


def insert_host_status_snapshot(
    created_at: str,
    device_id,
    ok,
    ip_status: str | None,
    raw_json: str,
) -> int:
    return _execute_write(
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
        return_lastrowid=True,
    )


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
    return _execute_write(
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
        return_lastrowid=True,
    )


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
    return _execute_write(
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
        return_lastrowid=True,
    )


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
    return _execute_write(
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
        return_lastrowid=True,
    )


def init_db():
    conn = get_main_connection()
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

    _execute_write(
        f"""
        DELETE FROM {table_name}
        WHERE {order_column} NOT IN (
            SELECT {order_column}
            FROM {table_name}
            ORDER BY {order_column} DESC
            LIMIT ?
        )
        """,
        (max_rows,),
    )


def insert_token(token: str, login_payload_json: str) -> int:
    row_id = _execute_write(
        """
        INSERT INTO auth_tokens (created_at, token, login_payload_json)
        VALUES (?, ?, ?)
        """,
        (now_rome_str(), token, login_payload_json),
        return_lastrowid=True,
    )

    cleanup_table_keep_latest("auth_tokens", AUTH_TOKEN_LIMIT)
    return row_id


def insert_user_info(token: str, payload_json: str) -> int:
    row_id = _execute_write(
        """
        INSERT INTO user_info_snapshots (created_at, token, payload_json)
        VALUES (?, ?, ?)
        """,
        (now_rome_str(), token, payload_json),
        return_lastrowid=True,
    )

    cleanup_table_keep_latest("user_info_snapshots", AUTH_USER_INFO_LIMIT)
    return row_id


def get_last_token_row(source: str | None = None):
    return _fetch_one_model(
        select(AuthToken).order_by(AuthToken.id.desc()),
        model_name="AuthToken",
        source=source,
    )


def get_last_user_info_row(source: str | None = None):
    return _fetch_one_model(
        select(UserInfoSnapshot).order_by(UserInfoSnapshot.id.desc()),
        model_name="UserInfoSnapshot",
        source=source,
    )


def get_last_token_value():
    row = get_last_token_row()
    if not row:
        return None
    return row["token"]


def insert_device_snapshot(device_row_key: str, update_time: str, json_data: str) -> int:
    row_id = _execute_write(
        """
        INSERT INTO device_snapshots (created_at, device_row_key, update_time, json_data)
        VALUES (?, ?, ?, ?)
        """,
        (now_rome_str(), device_row_key, update_time, json_data),
        return_lastrowid=True,
    )

    cleanup_table_keep_latest("device_snapshots", DEVICE_SNAPSHOT_LIMIT)
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
    row_id = _execute_write(
        """
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
        """,
        (
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
        ),
        return_lastrowid=True,
    )

    cleanup_table_keep_latest("device_snapshots_flat", DEVICE_SNAPSHOT_FLAT_LIMIT)
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

    query = f"""
        SELECT update_time, created_at, {metric_name} AS metric_value
        FROM device_snapshots_flat
        WHERE device_row_key = ?
          AND created_at >= ?
          AND created_at <= ?
        ORDER BY created_at ASC
    """
    return _fetch_all(query, (device_row_key, start_time, end_time))


##########################################################################
######### STATISTICS / AD-HOC READS ######################################
##########################################################################


def get_sensor_voltage_series(
    sensor_name: str,
    channel_index: int,
    since_created_at: str | None = None,
    database_url: str | None = None,
):
    conn = get_connection_for_database_url(database_url or DATABASE_URL)
    try:
        cur = conn.cursor()
        params = [sensor_name, channel_index]
        time_filter = ""

        if since_created_at is not None:
            time_filter = "AND created_at >= ?"
            params.append(since_created_at)

        cur.execute(
            f"""
            SELECT created_at, voltage
            FROM sensor_snapshots
            WHERE sensor_name = ?
              AND channel_index = ?
              AND voltage IS NOT NULL
              {time_filter}
            ORDER BY created_at ASC
            """,
            tuple(params),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def list_device_snapshots_flat_for_stats(
    *,
    hours: int | None = None,
    require_battery_capacity: bool = False,
    database_url: str | None = None,
):
    conn = get_connection_for_database_url(database_url or DATABASE_URL)
    try:
        cur = conn.cursor()
        query_lines = [
            "SELECT",
            "    created_at,",
            "    battery_voltage,",
            "    controller_charging_current,",
            "    load_percentage,",
            "    battery_capacity",
            "FROM device_snapshots_flat",
            "WHERE battery_voltage IS NOT NULL",
        ]
        params = []

        if require_battery_capacity:
            query_lines.append("  AND battery_capacity IS NOT NULL")

        if hours is not None:
            query_lines.append("  AND datetime(created_at) >= datetime('now', ?)")
            params.append(f"-{hours} hours")

        query_lines.append("ORDER BY created_at ASC")

        cur.execute("\n".join(query_lines), tuple(params))
        return [dict(row) for row in cur.fetchall()]
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