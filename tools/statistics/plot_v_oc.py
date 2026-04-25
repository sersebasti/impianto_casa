from email import parser
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

import matplotlib.pyplot as plt

DB_PATH = Path("data/solar.db")
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "v_oc_vs_battery_voltage.png"

# Coefficienti modello semplice
A_LOAD = 0.020
B_CHARGE = 0.010


def to_float(value):
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    s = (
        s.replace("V", "")
        .replace("v", "")
        .replace("A", "")
        .replace("a", "")
        .replace("%", "")
        .replace(",", ".")
        .strip()
    )

    try:
        return float(s)
    except Exception:
        return None


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                created_at,
                battery_voltage,
                controller_charging_current,
                load_percentage
            FROM device_snapshots_flat
            WHERE battery_voltage IS NOT NULL
            AND datetime(created_at) >= datetime('now', ?)
            ORDER BY created_at ASC
        """, (f"-{args.hours} hours",))

        times = []
        raw_values = []
        v_oc_values = []

        for row in cur.fetchall():
            battery_voltage = to_float(row["battery_voltage"])
            charge = to_float(row["controller_charging_current"])
            load = to_float(row["load_percentage"])

            if battery_voltage is None:
                continue

            if charge is None:
                charge = 0.0

            if load is None:
                load = 0.0

            dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")

            v_oc = (
                battery_voltage
                + A_LOAD * load
                - B_CHARGE * charge
            )

            times.append(dt)
            raw_values.append(battery_voltage)
            v_oc_values.append(v_oc)

    finally:
        conn.close()

    plt.figure(figsize=(15, 7))

    plt.plot(times, raw_values, label="battery_voltage raw")
    plt.plot(times, v_oc_values, label="v_oc stimata")

    plt.title("Battery voltage raw vs V_oc stimata")
    plt.xlabel("Tempo")
    plt.ylabel("Tensione [V]")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150)

    print(f"Grafico salvato in: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()


# Esempio di utilizzo:
# python plot_v_oc.py --hours 48
# docker compose exec battery_fit python plot_v_oc.py --hours 6        