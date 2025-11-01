from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os

# --------------------------
# Flask app setup
# --------------------------
app = Flask(__name__)
CORS(app)  # Allow any client (MT5, mobile, browser) to connect

# --------------------------
# Configuration
# --------------------------
SIGNAL_API_KEY = os.getenv("SIGNAL_API_KEY", "my_secret_key_123")
DB_PATH = os.path.join(os.path.dirname(__file__), "signals.db")

# --------------------------
# Initialize SQLite database
# --------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            type TEXT NOT NULL,
            volume REAL NOT NULL,
            sl REAL,
            tp REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --------------------------
# POST: Receive trade signal
# --------------------------
@app.route('/api/signal', methods=['POST'])
def receive_signal():
    try:
        # Force JSON parsing even if headers are weird (MT5 sends nonstandard Content-Type)
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "Bad JSON", "msg": str(e)}), 400

    # Check API key
    if not data or data.get('api_key') != SIGNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    # Save signal to DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''
            INSERT INTO signals (symbol, type, volume, sl, tp)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['symbol'], data['type'], data['volume'], data.get('sl'), data.get('tp')))
        conn.commit()
        conn.close()
        print("✅ Signal stored:", data)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------------------------
# GET: Retrieve new signals
# --------------------------
@app.route('/api/signal/<int:last_id>', methods=['GET'])
def get_signals(last_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM signals WHERE id > ? ORDER BY id LIMIT 10", (last_id,))
    rows = cur.fetchall()
    conn.close()

    signals = [{
        "id": row[0],
        "symbol": row[1],
        "type": row[2],
        "volume": row[3],
        "sl": row[4],
        "tp": row[5],
        "timestamp": row[6]
    } for row in rows]

    return jsonify(signals)

# --------------------------
# Health check
# --------------------------
@app.route('/health')
def health():
    return jsonify({"status": "server running", "db": "connected"})

# --------------------------
# Start Flask app
# --------------------------
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
