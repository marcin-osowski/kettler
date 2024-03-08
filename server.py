#!/usr/bin/env python3

import config

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
    conn.close()
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
    return render_template('index.html', rows=rows)

if __name__ == '__main__':
    waitress.serve(app, host=config.HTTP_HOST, port=config.HTTP_PORT)

