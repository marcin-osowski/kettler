#!/usr/bin/env python3

import config

from datetime import datetime, timedelta
from flask import Flask, render_template
import sqlite3
import waitress

app = Flask(__name__)

@app.route('/')
def index():
    conn = sqlite3.connect(config.DB_FILE)
    c = conn.cursor()
    c.execute("""
      SELECT start_time, distance_km, time_elapsed_sec, energy_kjoule
      FROM exercise_stats
      WHERE energy_kjoule > 50.0
      ORDER BY start_time DESC
    """)
    raw_rows = c.fetchall()
    rows = []
    for row in raw_rows:
        start_day = row[0][:10]
        distance = "%.1f km" % row[1]
        raw_time_sec = row[2]
        time_min = int(raw_time_sec / 60)
        time_sec = int(raw_time_sec % 60)
        time = "%d:%02d" % (time_min, time_sec)
        energy = "%.0f kJ" % row[3]

        rows.append({
            "start_day": start_day,
            "distance": distance,
            "time": time,
            "energy": energy,
        })
    c = conn.cursor()
    c.execute("""
      SELECT
        SUBSTR(start_time, 1, 10) AS start_day,
        SUM(energy_kjoule) as total_energy
      FROM exercise_stats
      WHERE energy_kjoule > 50.0 AND start_time > '2025-01-01'
      GROUP BY start_day
      ORDER BY start_day ASC
    """)
    raw_rows = c.fetchall()
    day_rows = []
    for row in raw_rows:
        day_rows.append({
            "day": row[0],
            "calories": row[1] / 4.184,
        })

    # Adding missing zeros
    min_day = min([row["day"] for row in day_rows])
    max_day = max([row["day"] for row in day_rows])
    min_day = datetime.strptime(min_day, "%Y-%m-%d")
    max_day = datetime.strptime(max_day, "%Y-%m-%d")
    day = min_day
    while day <= max_day:
        day_str = day.strftime("%Y-%m-%d")
        if day_str not in [row["day"] for row in day_rows]:
            day_rows.append({
                "day": day_str,
                "calories": "null",
            })
        day = day + timedelta(days=1)
    day_rows = sorted(day_rows, key=lambda x: x["day"])

    conn.close()
    return render_template('index.html', rows=rows, day_rows=day_rows)

if __name__ == '__main__':
    print(f"Running serve(host={config.HTTP_HOST}, port={config.HTTP_PORT})")
    waitress.serve(app, host=config.HTTP_HOST, port=config.HTTP_PORT)

