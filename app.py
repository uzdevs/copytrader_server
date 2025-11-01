from flask import Flask, request, jsonify
from datetime import datetime
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)  # allow access from all clients (mobile, MT5, etc.)

# --- Configuration ---
SIGNAL_API_KEY = os.getenv("SIGNAL_API_KEY", "my_secret_key_123")
DB_PATH = os.path.join(os.path.dirname(__file__), "signals.db")


# --- Initialize DB ---
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


# --- POST: Receive a trading signal ---
@app.route('/api/signal', methods=['POST'])
def receive_signal():
    data = request.get_json()
    if not data or data.get('api_key') != SIGNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

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


# --- GET: Retrieve signals after a specific ID ---
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


# --- Health check ---
@app.route('/health')
def health():
    return jsonify({"status": "server running", "db": "connected"})


# --- Start server ---
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
