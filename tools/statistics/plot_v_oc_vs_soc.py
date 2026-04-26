import argparse
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DB_PATH = Path("data/solar.db")
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "v_oc_vs_soc.png"

# Modello semplice
A_LOAD = 0.020
B_CHARGE = 0.008


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
    parser.add_argument("--hours", type=int, default=168)  # ultimi 7 giorni
    parser.add_argument("--min-count", type=int, default=3)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = []

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                created_at,
                battery_voltage,
                controller_charging_current,
                load_percentage,
                battery_capacity
            FROM device_snapshots_flat
            WHERE battery_voltage IS NOT NULL
              AND battery_capacity IS NOT NULL
              AND datetime(created_at) >= datetime('now', ?)
            ORDER BY created_at ASC
        """, (f"-{args.hours} hours",))

        for row in cur.fetchall():
            battery_voltage = to_float(row["battery_voltage"])
            charge = to_float(row["controller_charging_current"])
            load = to_float(row["load_percentage"])
            soc = to_float(row["battery_capacity"])

            if battery_voltage is None or soc is None:
                continue

            if soc >= 100:
                continue

            if charge is None:
                charge = 0.0

            if load is None:
                load = 0.0

            v_oc = battery_voltage + A_LOAD * load - B_CHARGE * charge

            rows.append((soc, v_oc))

    finally:
        conn.close()

    if not rows:
        print("Nessun dato disponibile.")
        return

    # Raggruppo per SOC intero
    groups = {}

    for soc, v_oc in rows:
        soc_bin = int(round(soc))
        groups.setdefault(soc_bin, []).append(v_oc)

    soc_values = []
    mean_values = []
    rms_values = []
    count_values = []

    for soc_bin in sorted(groups.keys()):
        values = np.array(groups[soc_bin], dtype=float)

        if len(values) < args.min_count:
            continue

        mean = float(np.mean(values))

        # Scarto quadratico medio rispetto alla media
        rms = float(np.sqrt(np.mean((values - mean) ** 2)))

        soc_values.append(soc_bin)
        mean_values.append(mean)
        rms_values.append(rms)
        count_values.append(len(values))

    if not soc_values:
        print("Dati insufficienti dopo il raggruppamento.")
        return

    plt.figure(figsize=(14, 7))

    plt.errorbar(
        soc_values,
        mean_values,
        yerr=rms_values,
        fmt="o-",
        capsize=4,
        label="V_oc media con scarto quadratico medio",
    )

    plt.title("V_oc media in funzione del SOC")
    plt.xlabel("SOC / battery_capacity [%]")
    plt.ylabel("V_oc stimata [V]")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150)

    print(f"Grafico salvato in: {OUTPUT_PATH}")
    print()
    print("Punti usati:")
    for soc, mean, rms, count in zip(soc_values, mean_values, rms_values, count_values):
        print(f"SOC={soc:3d}% | media={mean:.3f} V | RMS={rms:.3f} V | n={count}")


if __name__ == "__main__":
    main()