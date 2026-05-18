import json
import os
from flask import Blueprint, jsonify, request, render_template_string
from datetime import datetime, timedelta
from pathlib import Path
from solar_client import SolarClient
from logger import get_logger
from db import (
    get_last_token_row,
    get_last_user_info_row,
    get_device_metric_history,
    get_connection
)
import requests
import sqlite3

from zoneinfo import ZoneInfo
from tesla_client import exchange_code_for_token, refresh_tesla_token, wake_up_vehicle, get_vehicle_data
from commands import execute_command_by_config_id
from sqlalchemy import text

bp = Blueprint("api_endpoints", __name__)

logger = get_logger("endpoints")
client = SolarClient()


def now_rome():
    return datetime.now(ZoneInfo("Europe/Rome"))


@bp.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


##########################################################################
######### DEVICE INFO ####################################################
##########################################################################


@bp.route("/api/device-info", methods=["GET"])
def device_info():

    try:

        import socket
        import os

        hostname = socket.gethostname()

        host_mac = os.getenv(
            "HOST_MAC",
            ""
        )

        host_id = os.getenv(
            "HOST_ID",
            "backend_host"
        )

        ####################################################
        # REAL LAN IP
        ####################################################

        s = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        s.connect(("8.8.8.8", 80))

        local_ip = s.getsockname()[0]

        s.close()

        ####################################################
        # RESPONSE
        ####################################################

        return jsonify({

            "ok": True,

            "device_type":
                "backend_host",

            "service":
                "esprimo_flask",

            "service_id":
                host_id,

            "hostname":
                hostname,

            "ip":
                local_ip,

            "macaddress":
                host_mac,

        })

    except Exception as e:

        logger.exception(
            "Errore device_info | error=%s",
            e,
        )

        return jsonify({

            "ok": False,

            "error": str(e),

        }), 500



@bp.route("/api/login", methods=["POST", "GET"])
def login():
    try:
        data = client.do_login()
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/token/latest", methods=["GET"])
def token_latest():
    try:
        row = get_last_token_row()
        return jsonify({"ok": True, "row": row})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/user-info", methods=["GET"])
def user_info():
    try:
        data = client.get_user_info(save_to_db=True)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/user-info/latest", methods=["GET"])
def user_info_latest():
    try:
        row = get_last_user_info_row()
        return jsonify({"ok": True, "row": row})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/device-state/latest", methods=["GET"])
def device_state_latest():
    try:
        device_id = request.args.get("deviceId")
        data_source = int(request.args.get("dataSource", "1"))

        if not device_id:
            return jsonify({"ok": False, "error": "Parametro deviceId mancante"}), 400

        data = client.get_device_state_latest(
            device_id=device_id,
            data_source=data_source,
            save_to_db=True,
        )
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route(
    "/api/execute-config/<int:config_id>",
    methods=["GET", "POST"],
)
def execute_config(config_id):

    try:

        ################################################################
        # LOAD CONFIG
        ################################################################

        conn = get_connection()

        try:

            cur = conn.cursor()

            cur.execute("""

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

            """, (config_id,))

            row = cur.fetchone()

            if row:
                row = dict(row)

        finally:

            conn.close()

        if not row:

            return jsonify({

                "ok": False,
                "error": "config non trovata",
                "config_id": config_id,

            }), 404

        ################################################################
        # ENABLED CHECK
        ################################################################

        if not row["enabled"]:

            return jsonify({

                "ok": False,
                "error": "config disabilitata",
                "config_id": config_id,

            }), 400

        ################################################################
        # FAST DEVICE LOOKUP (LAST IP)
        ################################################################

        target_ip = None

        lanscan_conn = sqlite3.connect(

            "/app/lan_scanner_data/lan_scanner.db"

        )

        lanscan_conn.row_factory = sqlite3.Row

        try:

            cur = lanscan_conn.cursor()

            cur.execute("""

                SELECT
                    last_ip
                FROM device
                WHERE id = ?

            """, (

                row["device_id"],

            ))

            dev_row = cur.fetchone()

            if dev_row:

                dev_row = dict(dev_row)

                target_ip = (
                    dev_row.get("last_ip")
                )

        finally:

            lanscan_conn.close()

        ################################################################
        # FALLBACK LAN CHECK
        ################################################################

        if not target_ip:

            logger.warning(

                "Device IP non presente nel DB | "
                "device_id=%s | fallback LAN CHECK",

                row["device_id"]

            )

            lan_check_url = (
                "http://host.docker.internal:5001/"
                "lan_check"
            )

            try:

                lan_resp = requests.get(

                    lan_check_url,

                    timeout=20,

                )

                lan_resp.raise_for_status()

                lan_data = lan_resp.json()

            except Exception as e:

                logger.exception(
                    "LAN CHECK FAILED"
                )

                return jsonify({

                    "ok": False,

                    "error":
                        f"lan_check failed: {str(e)}",

                    "config_id":
                        config_id,

                    "lan_check_url":
                        lan_check_url,

                }), 500

            ################################################################
            # FIND TARGET DEVICE
            ################################################################

            target_device = None

            found_devices = (
                lan_data.get(
                    "detected_devices",
                    []
                )
            )

            for dev in found_devices:

                device_info = dev.get(
                    "device",
                    {}
                )

                current_device_id = (

                    device_info.get("id")

                    or dev.get("id")

                )

                if current_device_id == row["device_id"]:

                    target_device = dev

                    break

            ################################################################
            # DEVICE NOT FOUND
            ################################################################

            if not target_device:

                return jsonify({

                    "ok": False,

                    "error":
                        "device not found in LAN",

                    "config_id":
                        config_id,

                    "device_id":
                        row["device_id"],

                    "lan_check":
                        lan_data,

                }), 404

            ################################################################
            # LOG MISSING DEVICES
            ################################################################

            missing_devices = (
                lan_data.get(
                    "missing_devices",
                    []
                )
            )

            if missing_devices:

                logger.warning(
                    "Missing devices detected | devices=%s",
                    missing_devices,
                )

            ################################################################
            # TARGET IP
            ################################################################

            target_ip = (
                target_device.get("ip")
            )

        ################################################################
        # TARGET IP VALIDATION
        ################################################################

        if not target_ip:

            return jsonify({

                "ok": False,

                "error":
                    "target ip missing",

                "config_id":
                    config_id,

            }), 500

        logger.info(

            "TARGET DEVICE RESOLVED | "
            "device_id=%s | ip=%s",

            row["device_id"],
            target_ip,

        )

        ################################################################
        # PORT
        ################################################################

        port = (
            row["port"]
            or 80
        )

        ################################################################
        # ENDPOINT
        ################################################################

        endpoint_query = (
            row["endpoint_query"]
            or ""
        )

        endpoint_query = (
            endpoint_query.lstrip("/")
        )

        ################################################################
        # FINAL URL
        ################################################################

        url = (
            f"http://{target_ip}:{port}/"
            f"{endpoint_query}"
        )

        ################################################################
        # PAYLOAD
        ################################################################

        payload = None

        if row["payload"]:

            try:

                payload = json.loads(
                    row["payload"]
                )

            except Exception:

                payload = row["payload"]

        ################################################################
        # METHOD
        ################################################################

        method = (
            row["http_method"]
            or "GET"
        ).upper()

        ################################################################
        # DEBUG
        ################################################################

        logger.info("EXECUTE CONFIG")
        logger.info("config_id = %s", config_id)
        logger.info("device_id = %s", row["device_id"])
        logger.info("target_ip = %s", target_ip)
        logger.info("port = %s", port)
        logger.info("endpoint_query = %s", endpoint_query)
        logger.info("url = %s", url)
        logger.info("method = %s", method)
        logger.info("payload = %s", payload)

        ################################################################
        # EXECUTE REQUEST
        ################################################################

        if method == "POST":

            r = requests.post(

                url,

                json=payload,

                timeout=30,

            )

        else:

            r = requests.get(

                url,

                timeout=30,

            )

        ################################################################
        # RESPONSE JSON
        ################################################################

        try:

            response_payload = r.json()

        except Exception:

            response_payload = {

                "raw_text":
                    r.text

            }

        ################################################################
        # RETURN
        ################################################################

        return jsonify({

            "ok":
                r.ok,

            "config_id":
                config_id,

            "description":
                row["description"],

            "device_id":
                row["device_id"],

            "target_ip":
                target_ip,

            "port":
                port,

            "endpoint_query":
                endpoint_query,

            "url":
                url,

            "method":
                method,

            "payload":
                payload,

            "response":
                response_payload,

            "status_code":
                r.status_code,

        }), r.status_code

    except Exception as e:

        logger.exception(
            "execute_config FAILED"
        )

        return jsonify({

            "ok": False,

            "error":
                str(e),

            "config_id":
                config_id,

        }), 500


@bp.route("/api/chart-data", methods=["GET"])
def chart_data():
    try:
        device_row_key = request.args.get("device_row_key", "416360187241136128")
        metric = request.args.get("metric", "battery_voltage")
        period = request.args.get("period", "1h")
        start = request.args.get("start")
        end = request.args.get("end")

        now = now_rome()

        if start and end:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        else:
            period_map = {
                "1h": timedelta(hours=1),
                "3h": timedelta(hours=3),
                "6h": timedelta(hours=6),
                "12h": timedelta(hours=12),
                "24h": timedelta(hours=24),
            }
            delta = period_map.get(period, timedelta(hours=1))
            end_dt = now
            start_dt = now - delta

        start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        rows = get_device_metric_history(
            device_row_key=device_row_key,
            metric_name=metric,
            start_time=start_str,
            end_time=end_str,
        )

        labels = [row["created_at"] for row in rows]
        values = []
        for row in rows:
            value = row["metric_value"]
            try:
                values.append(float(value) if value is not None and value != "" else None)
            except Exception:
                values.append(None)

        return jsonify({
            "ok": True,
            "device_row_key": device_row_key,
            "metric": metric,
            "start": start_str,
            "end": end_str,
            "count": len(rows),
            "labels": labels,
            "values": values,
            "rows": rows,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@bp.route("/api/bms-communication", methods=["POST"])
def bms_communication():
    try:
        data = request.get_json(silent=True) or {}

        device_id = data.get("id")
        value = data.get("value")

        if not device_id:
            return jsonify({"ok": False, "error": "Campo id mancante"}), 400

        if value is None:
            return jsonify({"ok": False, "error": "Campo value mancante"}), 400

        device_id = str(device_id).strip()
        value = str(value).strip()

        if value not in ("1", "2"):
            return jsonify({
                "ok": False,
                "error": "Campo value non valido: usare '1' per ON oppure '2' per OFF"
            }), 400

        remote_data = client.set_bms_communication(
            device_id=device_id,
            value=value,
        )

        return jsonify({
            "ok": True,
            "id": device_id,
            "key": "bmsCommunicationSwitch",
            "value": value,
            "state": "ON" if value == "1" else "OFF",
            "remote_response": remote_data
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@bp.route("/api/bms-communication", methods=["GET"])
def bms_communication_get():
    try:
        device_id = request.args.get("id")

        if not device_id:
            return jsonify({"ok": False, "error": "Parametro id mancante"}), 400

        remote_data = client.get_bms_communication(device_id)

        info = remote_data.get("data", {}) or {}

        return jsonify({
            "ok": True,
            "id": device_id,
            "key": info.get("key"),
            "value": info.get("value"),
            "state": info.get("valueDisplay"),
            "remote_response": remote_data
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500





@bp.route("/chart", methods=["GET"])
def chart_page():
    return render_template_string("""
    <!doctype html>
    <html lang="it">
    <head>
        <meta charset="utf-8">
        <title>Grafico inverter</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .controls { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; align-items: end; }
            .group { display: flex; flex-direction: column; gap: 4px; }
            label { font-size: 14px; }
            select, input, button { padding: 6px 8px; font-size: 14px; }
            .quick-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
            canvas { max-width: 100%; height: 420px !important; }
        </style>
    </head>
    <body>
        <h2>Grafico storico inverter</h2>

        <div class="controls">
            <div class="group">
                <label>Device Row Key</label>
                <input type="text" id="device_row_key" value="416360187241136128">
            </div>

            <div class="group">
                <label>Metrica</label>
                <select id="metric">
                    <option value="battery_voltage">battery_voltage</option>
                    <option value="battery_capacity">battery_capacity</option>
                    <option value="controller_charging_current">controller_charging_current</option>
                    <option value="inverter_charging_current">inverter_charging_current</option>
                    <option value="load_percentage">load_percentage</option>
                    <option value="device_temp">device_temp</option>
                    <option value="pv_voltage">pv_voltage</option>
                </select>
            </div>

            <div class="group">
                <label>Periodo rapido</label>
                <div class="quick-buttons">
                    <button onclick="loadQuick('1h')">Ultima ora</button>
                    <button onclick="loadQuick('3h')">Ultime 3 ore</button>
                    <button onclick="loadQuick('6h')">Ultime 6 ore</button>
                    <button onclick="loadQuick('12h')">Ultime 12 ore</button>
                    <button onclick="loadQuick('24h')">Ultime 24 ore</button>
                </div>
            </div>

            <div class="group">
                <label>Data inizio</label>
                <input type="datetime-local" id="start">
            </div>

            <div class="group">
                <label>Data fine</label>
                <input type="datetime-local" id="end">
            </div>

            <div class="group">
                <label>&nbsp;</label>
                <button onclick="loadCustom()">Carica periodo custom</button>
            </div>
        </div>

        <div>
            <canvas id="historyChart"></canvas>
        </div>

        <pre id="info"></pre>

        <script>
            let chartInstance = null;

            async function fetchChartData(params) {
                const url = new URL('/api/chart-data', window.location.origin);
                Object.entries(params).forEach(([k, v]) => {
                    if (v !== null && v !== undefined && v !== '') {
                        url.searchParams.set(k, v);
                    }
                });

                const res = await fetch(url);
                return await res.json();
            }

            function renderChart(data) {
                const ctx = document.getElementById('historyChart').getContext('2d');

                if (chartInstance) {
                    chartInstance.destroy();
                }

                chartInstance = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: data.metric,
                            data: data.values,
                            fill: false,
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                ticks: {
                                    autoSkip: true,
                                    maxTicksLimit: 20
                                }
                            }
                        }
                    }
                });

                document.getElementById('info').textContent =
                    `device_row_key: ${data.device_row_key}
metrica: ${data.metric}
inizio: ${data.start}
fine: ${data.end}
punti: ${data.count}`;
            }

            async function loadQuick(period) {
                const device_row_key = document.getElementById('device_row_key').value;
                const metric = document.getElementById('metric').value;

                const data = await fetchChartData({
                    device_row_key,
                    metric,
                    period
                });

                if (!data.ok) {
                    alert(data.error || 'Errore');
                    return;
                }

                renderChart(data);
            }

            async function loadCustom() {
                const device_row_key = document.getElementById('device_row_key').value;
                const metric = document.getElementById('metric').value;
                const start = document.getElementById('start').value;
                const end = document.getElementById('end').value;

                if (!start || !end) {
                    alert('Inserisci data inizio e data fine');
                    return;
                }

                const data = await fetchChartData({
                    device_row_key,
                    metric,
                    start,
                    end
                });

                if (!data.ok) {
                    alert(data.error || 'Errore');
                    return;
                }

                renderChart(data);
            }

            loadQuick('1h');
        </script>
    </body>
    </html>
    """)

@bp.route("/sensors", methods=["GET"])
def sensors_page():

    return render_template_string("""
    <!doctype html>
    <html lang="it">

    <head>
        <meta charset="utf-8">

        <title>Dashboard Sensori</title>

        <style>

            body {
                font-family: Arial, sans-serif;
                background: #f3f4f6;
                margin: 0;
                padding: 20px;
            }

            h1 {
                margin-bottom: 20px;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
                gap: 20px;
            }

            .card {
                background: white;
                border-radius: 16px;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }

            .device-type {
                display: inline-block;
                background: #dbeafe;
                color: #1d4ed8;
                padding: 4px 10px;
                border-radius: 999px;
                font-size: 12px;
                margin-top: 8px;
            }

            .measurements {
                margin-top: 20px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            button {
                border: 1px solid #d1d5db;
                background: #f9fafb;
                border-radius: 10px;
                padding: 12px;
                cursor: pointer;
                text-align: left;
                transition: 0.2s;
            }

            button:hover {
                background: #eff6ff;
                border-color: #60a5fa;
            }

            pre {
                background: #111827;
                color: #f9fafb;
                padding: 16px;
                border-radius: 12px;
                overflow: auto;
                margin-top: 30px;
            }

        </style>
    </head>

    <body>

        <h1>Dashboard Sensori</h1>

        <div id="devices" class="grid"></div>

        <pre id="output">Nessuna misura selezionata</pre>

        <script>

            async function loadDevices() {

                const res = await fetch('/api/devices');

                const devices = await res.json();

                const container =
                    document.getElementById('devices');

                for (const dev of devices) {

                    const card =
                        document.createElement('div');

                    card.className = 'card';

                    card.innerHTML = `
                        <h2>${dev.description}</h2>

                        <div class="device-type">
                            ${dev.device_type}
                        </div>

                        <div style="margin-top:8px;">
                            Device ID: ${dev.id}
                        </div>

                        <div
                            class="measurements"
                            id="measurements-${dev.id}"
                        >
                        </div>
                    `;

                    container.appendChild(card);

                    await loadMeasurements(dev.id);
                }
            }

            async function loadMeasurements(deviceId) {

                const res = await fetch(
                    `/api/sensor-measurements-config?device_id=${deviceId}`
                );

                const data = await res.json();

                console.log(
                    'Measurements device',
                    deviceId,
                    data
                );

                const container =
                    document.getElementById(
                        `measurements-${deviceId}`
                    );

                if (!data.ok) {

                    container.innerHTML =
                        '<div>Errore caricamento misure</div>';

                    return;
                }

                if (!data.rows || data.rows.length === 0) {

                    container.innerHTML =
                        '<div>Nessuna misura configurata</div>';

                    return;
                }

                for (const row of data.rows) {

                    const btn =
                        document.createElement('button');

                    btn.innerText =
                        row.description || row.endpoint_query;

                    btn.onclick = () =>
                        executeMeasurement(row);

                    container.appendChild(btn);
                }
            }

            async function executeMeasurement(row) {

                try {

                    const url =
                        `/api/device-measurement?device_id=${row.device_id}&endpoint_query=${encodeURIComponent(row.endpoint_query)}`;

                    console.log('Measurement URL:', url);

                    const res = await fetch(url);

                    const data = await res.json();

                    document.getElementById('output').textContent =
                        JSON.stringify(data, null, 2);

                } catch (err) {

                    document.getElementById('output').textContent =
                        'Errore: ' + err;
                }
            }

            loadDevices();

        </script>

    </body>

    </html>
    """)


@bp.route("/api/devices", methods=["GET"])
def api_devices():

    try:

        import requests

        r = requests.get(
            "http://host.docker.internal:5001/devices",
            timeout=10,
        )

        r.raise_for_status()

        data = r.json()

        return jsonify(data)

    except Exception as e:

        logger.exception(
            "Errore api_devices | error=%s",
            e,
        )

        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


@bp.route("/api/device-measurement", methods=["GET"])
def api_device_measurement():

    try:

        import requests

        device_id = request.args.get("device_id")
        endpoint_query = request.args.get("endpoint_query")

        url = (
            f"http://host.docker.internal:5001/"
            f"{device_id}/measurment"
            f"?endpoint={endpoint_query}"
        )

        r = requests.get(
            url,
            timeout=20,
        )

        r.raise_for_status()

        data = r.json()

        return jsonify(data)

    except Exception as e:

        logger.exception(
            "Errore api_device_measurement | error=%s",
            e,
        )

        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


@bp.route("/api/sensor-measurements-config", methods=["GET"])
def sensor_measurements_config():

    try:

        import sqlite3

        device_id = request.args.get("device_id")

        conn = sqlite3.connect("data/solar.db")

        conn.row_factory = sqlite3.Row

        cur = conn.cursor()

        if device_id:

            cur.execute(
                '''
                SELECT *
                FROM sensor_measurements_config
                WHERE device_id = ?
                AND enabled = 1
                ORDER BY id
                ''',
                (device_id,)
            )

        else:

            cur.execute(
                '''
                SELECT *
                FROM sensor_measurements_config
                WHERE enabled = 1
                ORDER BY device_id, id
                '''
            )

        rows = [
            dict(row)
            for row in cur.fetchall()
        ]

        conn.close()

        return jsonify({
            "ok": True,
            "count": len(rows),
            "rows": rows,
        })

    except Exception as e:

        logger.exception(
            "Errore sensor_measurements_config | error=%s",
            e,
        )

        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


#########################################################################
######### ENDPINTS FOR COMMANDS #########################################
#########################################################################

@bp.route("/api/device-command", methods=["POST"])
def api_device_command():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        config_id = data.get(
            "config_id"
        )

        if not config_id:

            return jsonify({
                "ok": False,
                "error": "config_id mancante",
            }), 400

        result = execute_command_by_config_id(
            logger=logger,
            config_id=int(config_id),
        )

        return jsonify(result)

    except Exception as e:

        logger.exception(
            "Errore api_device_command | error=%s",
            e,
        )

        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500



##########################################################################
######### REFRESH RELAY STATUS SNAPSHOTS #################################
##########################################################################

@bp.route("/api/refresh-relay-status", methods=["POST"])
def refresh_relay_status():

    try:

        from polling_tasks import (
            acquire_and_save_relays_status_data
        )

        logger.info("")
        logger.info("############################################################")
        logger.info("############ MANUAL RELAY STATUS REFRESH ###################")
        logger.info("############################################################")

        result = (
            acquire_and_save_relays_status_data(
                logger
            )
        )

        return jsonify({

            "ok": True,

            "message":
                "Relay status snapshots aggiornati",

            "result": result,

        })

    except Exception as e:

        logger.exception(
            "Errore refresh_relay_status | error=%s",
            e,
        )

        return jsonify({

            "ok": False,

            "error": str(e),

        }), 500



##########################################################################
######### ENDPINTS FOR TESLA API #########################################
##########################################################################

TESLA_CALLBACK_FILE = Path("data/tesla_callback_code.json")


@bp.route("/callback", methods=["GET"])
def tesla_callback():
    try:
        code = request.args.get("code")
        state = request.args.get("state")
        error = request.args.get("error")
        error_description = request.args.get("error_description")

        if error:
            return jsonify({
                "ok": False,
                "error": error,
                "error_description": error_description,
            }), 400

        if not code:
            return jsonify({"ok": False, "error": "Code Tesla mancante"}), 400

        data = exchange_code_for_token(code=code)

        return jsonify({
            "ok": True,
            "message": "Code ricevuto, token Tesla ottenuto e salvato",
            "has_access_token": bool(data.get("access_token")),
            "has_refresh_token": bool(data.get("refresh_token")),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type"),
            "saved_at": data.get("saved_at"),
            "state": state,
        })

    except Exception as e:
        logger.exception("Errore callback Tesla | error=%s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    
@bp.route("/api/tesla/refresh-token", methods=["POST", "GET"])
def tesla_refresh_token():
    try:
        data = refresh_tesla_token()

        return jsonify({
            "ok": True,
            "message": "Token Tesla aggiornato correttamente",
            "has_access_token": bool(data.get("access_token")),
            "has_refresh_token": bool(data.get("refresh_token")),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type"),
            "saved_at": data.get("saved_at"),
            "audience": data.get("audience"),
        })

    except Exception as e:
        logger.exception("Errore refresh token Tesla | error=%s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    

@bp.route("/api/tesla/wake-up", methods=["POST", "GET"])
def tesla_wake_up():
    try:
        vin = request.args.get("vin") or os.getenv("TESLA_VIN", "")

        if not vin:
            return jsonify({"ok": False, "error": "TESLA_VIN mancante"}), 500

        data = wake_up_vehicle(vin)

        return jsonify({
            "ok": True,
            "vin": vin,
            "command": "wake_up",
            "response": data,
        })

    except Exception as e:
        logger.exception("Errore wake_up Tesla | error=%s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    
@bp.route("/api/tesla/vehicle-data", methods=["GET"])
def tesla_vehicle_data():
    try:
        vin = request.args.get("vin") or os.getenv("TESLA_VIN", "")

        if not vin:
            return jsonify({"ok": False, "error": "TESLA_VIN mancante"}), 500

        data = get_vehicle_data(vin)

        return jsonify({
            "ok": True,
            "vin": vin,
            "data": data,
        })

    except Exception as e:
        logger.exception("Errore vehicle_data Tesla | error=%s", e)
        return jsonify({"ok": False, "error": str(e)}), 500