# Tools statistics

Script di analisi statistica per i dati dell'inverter salvati in SQLite.

- Database utilizzato
-- data/solar.db

- Tabella principale
-- device_snapshots_flat

--------------------------------------------------

# Avvio container statistiche

- Container dedicato
-- battery_fit

- Avvio
-- docker compose up -d battery_fit

- Verifica stato
-- docker compose ps

--------------------------------------------------

# 1. Fit coefficienti V_oc

- Script
-- tools/statistics/fit_battery_correction.py

- Comando
-- docker compose exec battery_fit python tools/statistics/fit_battery_correction.py

- Cosa fa
-- legge i dati storici dal database
-- usa battery_voltage
-- usa load_percentage
-- usa controller_charging_current
-- calcola i coefficienti migliori
-- stima la tensione a vuoto della batteria
-- mostra score e anteprima risultati

- Formula obiettivo
-- v_oc = battery_voltage + a*load_percentage - b*controller_charging_current

- Formula interna script
-- v_oc = battery_voltage + x1*controller_charging_current - x2*load_percentage

- Relazione coefficienti
-- a = -x2
-- b = -x1

--------------------------------------------------

# 2. Grafico battery_voltage vs V_oc

- Script
-- tools/statistics/plot_v_oc.py

- Comando base
-- docker compose exec battery_fit python tools/statistics/plot_v_oc.py --hours 24

- Cosa fa
-- genera un grafico con due linee
-- linea 1 = battery_voltage grezza
-- linea 2 = v_oc stimata
-- utile per vedere se v_oc è più liscia della curva originale

- Esempi
-- docker compose exec battery_fit python tools/statistics/plot_v_oc.py --hours 6
-- docker compose exec battery_fit python tools/statistics/plot_v_oc.py --hours 24
-- docker compose exec battery_fit python tools/statistics/plot_v_oc.py --hours 72
-- docker compose exec battery_fit python tools/statistics/plot_v_oc.py --hours 168

- Output
-- logs/v_oc_vs_battery_voltage.png

--------------------------------------------------

# 3. Grafico V_oc vs SOC

- Script
-- tools/statistics/plot_v_oc_vs_soc.py

- Comando base
-- docker compose exec battery_fit python tools/statistics/plot_v_oc_vs_soc.py --hours 168

- Cosa fa
-- asse X = SOC / battery_capacity
-- asse Y = media dei valori v_oc
-- esclude SOC = 100%
-- raggruppa per SOC intero
-- mostra barre errore come scarto quadratico medio

- Esempi
-- docker compose exec battery_fit python tools/statistics/plot_v_oc_vs_soc.py --hours 24
-- docker compose exec battery_fit python tools/statistics/plot_v_oc_vs_soc.py --hours 168
-- docker compose exec battery_fit python tools/statistics/plot_v_oc_vs_soc.py --hours 720

- Output
-- logs/v_oc_vs_soc.png

--------------------------------------------------

# Coefficienti attuali consigliati

- Modello semplice
-- v_oc = battery_voltage + 0.020*load_percentage - 0.010*controller_charging_current

- Interpretazione
-- il carico abbassa la tensione letta
-- la carica alza la tensione letta
-- la formula compensa questi effetti

--------------------------------------------------

# Note operative

- Dopo modifiche agli script
-- docker compose up -d --build battery_fit

- Esecuzione generica
-- docker compose exec battery_fit python tools/statistics/NOME_SCRIPT.py

- Cartella output grafici
-- logs/