from flask import Flask, request, jsonify
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)
SIGNAL_API_KEY = "my_secret_key_123"

# Initialize DB
def init_db():
    conn = sqlite3.connect('signals.db')
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

@app.route('/api/signal', methods=['POST'])
def receive_signal():
    data = request.get_json()
    if not data or data.get('api_key') != SIGNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    # Save to DB
    conn = sqlite3.connect('signals.db')
    conn.execute('''
        INSERT INTO signals (symbol, type, volume, sl, tp)
        VALUES (?, ?, ?, ?, ?)
    ''', (data['symbol'], data['type'], data['volume'], data.get('sl'), data.get('tp')))
    conn.commit()
    conn.close()

    print("✅ Signal stored:", data)
    return jsonify({"status": "ok"})

@app.route('/api/signal/<int:last_id>', methods=['GET'])
def get_signals(last_id):
    # Simple client polling (add auth later)
    conn = sqlite3.connect('signals.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM signals WHERE id > ? ORDER BY id LIMIT 10", (last_id,))
    rows = cur.fetchall()
    conn.close()

    signals = []
    for row in rows:
        signals.append({
            "id": row[0],
            "symbol": row[1],
            "type": row[2],
            "volume": row[3],
            "sl": row[4],
            "tp": row[5],
            "timestamp": row[6]
        })
    return jsonify(signals)

@app.route('/health')
def health():
    return jsonify({"status": "server running with DB"})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)