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


CREATE TABLE IF NOT EXISTS tesla_vehicle_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,

    vin TEXT NOT NULL,
    state TEXT,

    battery_level REAL,
    charging_state TEXT,
    charge_limit_soc REAL,
    charger_power REAL,

    inside_temp REAL,
    outside_temp REAL,

    locked INTEGER,

    charge_port_door_open INTEGER,
    charge_port_latch TEXT,
    charge_port_color TEXT,
    conn_charge_cable TEXT
);

CREATE INDEX IF NOT EXISTS idx_tesla_vehicle_snapshots_vin_created_at
ON tesla_vehicle_snapshots (vin, created_at);


CREATE TABLE IF NOT EXISTS sensor_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    sensor_name TEXT NOT NULL,
    sensor_type TEXT,
    ip TEXT,
    macaddress TEXT,
    endpoint TEXT,
    channel_index INTEGER,
    ok INTEGER,
    voltage REAL,
    current REAL,
    power REAL,
    power_factor REAL,
    frequency REAL,
    energy REAL,
    total_power REAL,
    raw_json TEXT
);
/*
CREATE TABLE sensor_measurements_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    device_id INTEGER NOT NULL,

    call_type TEXT NOT NULL,

    http_method TEXT DEFAULT 'GET',

    endpoint_query TEXT NOT NULL,

    payload TEXT,

    response_structure TEXT,

    description TEXT,

    enabled INTEGER DEFAULT 1
);

-- Shelly EM3 fase 1
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    2,
    'measurment',
    'GET',
    'emeter/1',
    NULL,
    '{
        "response": {
            "current": "<float>",
            "is_valid": "<bool>",
            "pf": "<float>",
            "power": "<float>",
            "total": "<float>",
            "total_returned": "<float>",
            "voltage": "<float>"
        }
    }',
    'Assorbimento Totale da Manyi',
    1
);

-- Shelly EM3 fase 2
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    2,
    'measurment',
    'GET',
    'emeter/2',
    NULL,
    '{
        "response": {
            "current": "<float>",
            "is_valid": "<bool>",
            "pf": "<float>",
            "power": "<float>",
            "total": "<float>",
            "total_returned": "<float>",
            "voltage": "<float>"
        }
    }',
    'Assorbimento Auto da Manyi',
    1
);

-- Shelly status
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    2,
    'measurment',
    'GET',
    'status',
    NULL,
    '{
        "response": {
            "actions_stats": {},
            "cloud": {},
            "emeters": [],
            "mqtt": {},
            "relays": [],
            "update": {},
            "wifi_sta": {}
        }
    }',
    'Shelly Status',
    1
);

-- ESP32 Fronius power_sensor
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    1,
    'measurment',
    'GET',
    'power_sensor&id=pz1',
    NULL,
    '{
        "response": {
            "data": {
                "alarm": "<int>",
                "current": "<float>",
                "energy": "<float>",
                "frequency": "<float>",
                "power": "<float>",
                "power_factor": "<float>",
                "voltage": "<float>"
            },
            "ok": "<bool>"
        }
    }',
    'Produzione Fronius',
    1
);

-- ESP32 Fronius status
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    1,
    'measurment',
    'GET',
    'status',
    NULL,
    '{
        "response": {
            "heap_free": "<int>",
            "ip": "<string>",
            "mac_sta": "<string>",
            "name": "<string>",
            "rssi": "<int>",
            "ssid": "<string>",
            "uptime_s": "<int>",
            "version": "<string>"
        }
    }',
    'ESP32 Fronius Status',
    1
);

-- ESP32 Main Status
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'status',
    NULL,
    '{
        "response": {
            "heap_free": "<int>",
            "ip": "<string>",
            "mac_sta": "<string>",
            "name": "<string>",
            "rssi": "<int>",
            "ssid": "<string>",
            "uptime_s": "<int>",
            "version": "<string>"
        }
    }',
    'ESP32 Main Status',
    1
);

-- Assorbimento Input Manyi
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'power&voltage_sensor_id=v1&current_sensor_id=c1&n=800&sr=4000&fast=1&phase_shift=1',
    NULL,
    '{
        "response": {
            "amps_rms": "<float>",
            "power_w": "<float>",
            "volts_rms": "<float>",
            "power_factor": "<float>"
        }
    }',
    'Assorbimento Input Manyi',
    1
);

-- Assorbimento Totale da ENEL BIS
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'power&voltage_sensor_id=v1&current_sensor_id=c2&n=800&sr=4000&fast=1&phase_shift=1',
    NULL,
    '{
        "response": {
            "amps_rms": "<float>",
            "power_w": "<float>",
            "volts_rms": "<float>",
            "power_factor": "<float>"
        }
    }',
    'Assorbimento Totale da ENEL BIS',
    1
);

-- Assorbimento Auto da ENEL
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'power&voltage_sensor_id=v1&current_sensor_id=c3&n=800&sr=4000&fast=1&phase_shift=1',
    NULL,
    '{
        "response": {
            "amps_rms": "<float>",
            "power_w": "<float>",
            "volts_rms": "<float>",
            "power_factor": "<float>"
        }
    }',
    'Assorbimento Auto da ENEL',
    1
);

-- Assorbimento Casa da ENEL
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'power&voltage_sensor_id=v1&current_sensor_id=c4&n=800&sr=4000&fast=1&phase_shift=1',
    NULL,
    '{
        "response": {
            "amps_rms": "<float>",
            "power_w": "<float>",
            "volts_rms": "<float>",
            "power_factor": "<float>"
        }
    }',
    'Assorbimento Casa da ENEL',
    1
);

-- Relay status
INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'relay',
    NULL,
    '{
        "response": [
            {
                "id": "<string>",
                "is_on": "<bool>",
                "real_state": "<bool|null>"
            }
        ]
    }',
    'Stato Relays e Controllo',
    1
);

INSERT INTO sensor_measurements_config (
    device_id,
    call_type,
    http_method,
    endpoint_query,
    payload,
    response_structure,
    description,
    enabled
)
VALUES (
    3,
    'measurment',
    'GET',
    'power_sensor&id=pz1',
    NULL,
    '{
        "response": {
            "data": {
                "alarm": "<int>",
                "current": "<float>",
                "energy": "<float>",
                "frequency": "<float>",
                "power": "<float>",
                "power_factor": "<float>",
                "voltage": "<float>"
            },
            "ok": "<bool>"
        }
    }',
    'Assorbimento Totale da ENEL',
    1
);


*/