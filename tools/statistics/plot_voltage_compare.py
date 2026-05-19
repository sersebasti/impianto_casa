'''

python tools/statistics/plot_voltage_compare.py --last-hours 6

python tools/statistics/plot_voltage_compare.py \
  --shelly-name "Shelly EM3 Assorbimenti da ENEL L2" \
  --shelly-channel 1 \
  --last-hours 12 \
  --out tools/statistics/voltage_compare_12h.png

'''

import argparse
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from db import build_sqlite_database_url, get_sensor_voltage_series


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/solar.db")
    p.add_argument("--out", default="tools/statistics/voltage_compare_fronius_shelly.png")
    p.add_argument("--last-hours", type=float, default=None)

    p.add_argument("--fronius-name", default="Produzione Fronius")
    p.add_argument("--fronius-channel", type=int, default=1)

    p.add_argument("--shelly-name", default="Shelly EM3 Assorbimenti da ENEL L1")
    p.add_argument("--shelly-channel", type=int, default=0)

    return p.parse_args()


def load_series(db_path, sensor_name, channel_index, last_hours=None):
    since_created_at = None
    if last_hours is not None:
        since = datetime.now() - timedelta(hours=last_hours)
        since_created_at = since.isoformat(timespec="seconds")

    rows = get_sensor_voltage_series(
        sensor_name=sensor_name,
        channel_index=channel_index,
        since_created_at=since_created_at,
        database_url=build_sqlite_database_url(db_path),
    )

    times = []
    values = []

    for row in rows:
        try:
            times.append(datetime.fromisoformat(row["created_at"]))
            values.append(float(row["voltage"]))
        except Exception:
            continue

    return times, values


args = parse_args()

series = [
    (args.fronius_name, args.fronius_channel),
    (args.shelly_name, args.shelly_channel),
]

plt.figure(figsize=(14, 6))

found = False

for sensor_name, channel_index in series:
    times, values = load_series(
        args.db,
        sensor_name,
        channel_index,
        args.last_hours,
    )

    print(sensor_name, channel_index, "records:", len(values))

    if values:
        found = True
        plt.plot(times, values, label=f"{sensor_name} ch {channel_index}")

if not found:
    raise SystemExit("Nessun dato trovato")

title = "Confronto tensione Fronius / Shelly"
if args.last_hours:
    title += f" - ultime {args.last_hours:g} ore"

plt.title(title)
plt.xlabel("Tempo")
plt.ylabel("Volt")
plt.legend()
plt.grid(True)

ax = plt.gca()
locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
formatter = mdates.DateFormatter("%d/%m %H:%M")
ax.xaxis.set_major_locator(locator)
ax.xaxis.set_major_formatter(formatter)

plt.xticks(rotation=30, ha="right")
plt.tight_layout()

out_path = Path(args.out)
out_path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out_path, dpi=150)

print(f"Grafico salvato in: {out_path}")
