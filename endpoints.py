from flask import Blueprint, jsonify, request, render_template_string
from datetime import datetime, timedelta

from solar_client import SolarClient
from logger import get_logger
from db import (
    get_last_token_row,
    get_last_user_info_row,
    get_device_metric_history,
)
from zoneinfo import ZoneInfo

bp = Blueprint("api_endpoints", __name__)

logger = get_logger("endpoints")
client = SolarClient()


def now_rome():
    return datetime.now(ZoneInfo("Europe/Rome"))


@bp.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


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