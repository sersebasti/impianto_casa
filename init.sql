CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    token TEXT NOT NULL,
    login_payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_created_at
    ON auth_tokens (created_at);


CREATE TABLE IF NOT EXISTS user_info_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    token TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_info_snapshots_created_at
    ON user_info_snapshots (created_at);


CREATE TABLE IF NOT EXISTS device_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_row_key TEXT NOT NULL,
    update_time TEXT NULL,
    json_data TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_device_row_key
    ON device_snapshots (device_row_key);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_created_at
    ON device_snapshots (created_at);


CREATE TABLE IF NOT EXISTS device_snapshots_flat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_row_key TEXT NOT NULL,
    update_time TEXT NULL,

    inverter_program_version TEXT NULL,
    internal_model TEXT NULL,
    input_voltage TEXT NULL,
    input_frequency TEXT NULL,
    output_voltage TEXT NULL,
    output_frequency TEXT NULL,
    battery_voltage TEXT NULL,
    battery_capacity TEXT NULL,
    inverter_charging_current TEXT NULL,
    load_percentage TEXT NULL,
    device_temp TEXT NULL,
    machine_status_code TEXT NULL,
    system_run_time TEXT NULL,
    system_operation_status TEXT NULL,
    battery_number_in_series TEXT NULL,
    controller_program_version TEXT NULL,
    pv_voltage TEXT NULL,
    controller_charging_current TEXT NULL,
    controller_temp TEXT NULL,
    controller_status_code TEXT NULL,
    controller_connection_status TEXT NULL,
    controller_charging_status TEXT NULL,
    inverter_charge_status TEXT NULL,
    battery_voltage_is_full TEXT NULL,
    controller_malfunction_alarm TEXT NULL,
    controller_warning_alarm TEXT NULL,
    inverter_fault_alarm TEXT NULL,
    inverter_warning_alarm TEXT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_flat_device_row_key
    ON device_snapshots_flat (device_row_key);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_flat_created_at
    ON device_snapshots_flat (created_at);