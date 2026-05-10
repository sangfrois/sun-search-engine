from flask import Flask, render_template_string
import sqlite3
import datetime

app = Flask(__name__)

HTML = '''<!DOCTYPE html>
<html>
<head>
<title>SUN Dashboard</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #121212; color: #e0e0e0; padding: 40px; }
  h1 { color: #ffab00; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .card { background: #1e1e1e; padding: 20px; border-radius: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #333; }
</style>
</head>
<body>
  <h1>☀️ SUN Telemetry (Local Only)</h1>
  <div class="grid">
    <div class="card">
      <h2>Recent Searches</h2>
      <table><tr><th>Time</th><th>Query</th></tr>
      {% for row in recent %}<tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>{% endfor %}
      </table>
    </div>
    <div class="card">
      <h2>Top RL Preferences (Topics)</h2>
      <table><tr><th>Word</th><th>Weight</th></tr>
      {% for row in preferences %}<tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>{% endfor %}
      </table>
    </div>
  </div>
</body>
</html>'''

@app.route('/')
def index():
    conn = sqlite3.connect('/app/data/sun_rl.db')
    c = conn.cursor()
    c.execute("SELECT datetime(timestamp, 'localtime'), query FROM history ORDER BY timestamp DESC LIMIT 20")
    recent = c.fetchall()
    c.execute("SELECT word, weight FROM preferences ORDER BY weight DESC LIMIT 20")
    preferences = c.fetchall()
    conn.close()
    return render_template_string(HTML, recent=recent, preferences=preferences)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
