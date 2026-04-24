import sqlite3
from pathlib import Path

DB_PATH = Path("data/solar.db")


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


def load_rows():
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
            ORDER BY created_at ASC
        """)

        rows = []
        for r in cur.fetchall():
            battery_voltage = to_float(r["battery_voltage"])
            charging_current = to_float(r["controller_charging_current"])
            load_percentage = to_float(r["load_percentage"])

            if battery_voltage is None:
                continue

            rows.append({
                "created_at": r["created_at"],
                "battery_voltage": battery_voltage,
                "controller_charging_current": charging_current if charging_current is not None else 0.0,
                "load_percentage": load_percentage if load_percentage is not None else 0.0,
            })

        return rows

    finally:
        conn.close()


def estimate_v_oc(row, x1, x2):
    """
    Stima V_oc, cioè la tensione equivalente a vuoto.

    Formula:
    v_oc = battery_voltage + x1*controller_charging_current - x2*load_percentage
    """
    return (
        row["battery_voltage"]
        + x1 * row["controller_charging_current"]
        - x2 * row["load_percentage"]
    )


def score(rows, x1, x2):
    """
    Più basso è, meglio è.

    Penalizza:
    - salti improvvisi della V_oc stimata
    - coefficienti troppo aggressivi
    """
    if len(rows) < 3:
        return float("inf")

    jumps = []
    prev = estimate_v_oc(rows[0], x1, x2)

    for row in rows[1:]:
        cur = estimate_v_oc(row, x1, x2)
        diff = cur - prev
        jumps.append(diff * diff)
        prev = cur

    smooth_error = sum(jumps) / len(jumps)
    penalty = 0.001 * (x1 * x1 + x2 * x2)

    return smooth_error + penalty


def find_best_coefficients(rows):
    import numpy as np

    battery = np.array([r["battery_voltage"] for r in rows], dtype=float)
    charge = np.array([r["controller_charging_current"] for r in rows], dtype=float)
    load = np.array([r["load_percentage"] for r in rows], dtype=float)

    best = {
        "x1": 0.0,
        "x2": 0.0,
        "score": score(rows, 0.0, 0.0),
    }

    x1_values = np.arange(-0.100, 0.101, 0.002)
    x2_values = np.arange(-0.100, 0.101, 0.002)

    total = len(x1_values) * len(x2_values)
    done = 0

    for x1 in x1_values:
        for x2 in x2_values:
            v_oc = battery + x1 * charge - x2 * load
            diffs = np.diff(v_oc)

            smooth_error = float(np.mean(diffs * diffs))
            penalty = 0.001 * float(x1 * x1 + x2 * x2)
            s = smooth_error + penalty

            done += 1
            if done % 1000 == 0:
                print(
                    f"fit progress: {done}/{total} | best_score={best['score']:.8f}",
                    flush=True,
                )

            if s < best["score"]:
                best = {
                    "x1": float(x1),
                    "x2": float(x2),
                    "score": float(s),
                }

    return best


def print_preview(rows, x1, x2, limit=30):
    print()
    print("ANTEPRIMA V_OC STIMATA")
    print("-" * 100)
    print(f"{'created_at':20} {'raw':>8} {'v_oc':>8} {'carica_A':>10} {'carico_%':>10}")
    print("-" * 100)

    step = max(1, len(rows) // limit)

    for row in rows[::step][:limit]:
        raw = row["battery_voltage"]
        v_oc = estimate_v_oc(row, x1, x2)
        charge = row["controller_charging_current"]
        load = row["load_percentage"]

        print(
            f"{row['created_at']:20} "
            f"{raw:8.3f} "
            f"{v_oc:8.3f} "
            f"{charge:10.3f} "
            f"{load:10.3f}"
        )


def main():
    rows = load_rows()

    print(f"Record caricati: {len(rows)}")

    if len(rows) < 20:
        print("Troppi pochi dati per fare un fit sensato.")
        return

    base_score = score(rows, 0.0, 0.0)
    best = find_best_coefficients(rows)

    x1 = best["x1"]
    x2 = best["x2"]

    print()
    print("RISULTATO FIT V_OC")
    print("=" * 60)
    print(f"x1 = {x1:.6f}")
    print(f"x2 = {x2:.6f}")
    print(f"score senza correzione = {base_score:.8f}")
    print(f"score con V_oc stimata = {best['score']:.8f}")

    if base_score > 0 and best["score"] > 0:
        improvement = (1.0 - best["score"] / base_score) * 100.0
        print(f"miglioramento stimato  = {improvement:.2f}%")

    print()
    print("Formula da usare:")
    print()
    print(
        "v_oc = "
        "battery_voltage "
        f"+ ({x1:.6f}) * controller_charging_current "
        f"- ({x2:.6f}) * load_percentage"
    )

    print()
    print("Formula interpretata fisicamente:")
    print()
    print(
        "v_oc = "
        "battery_voltage "
        f"+ ({-x2:.6f}) * load_percentage "
        f"+ ({x1:.6f}) * controller_charging_current"
    )

    print_preview(rows, x1, x2)


if __name__ == "__main__":
    main()