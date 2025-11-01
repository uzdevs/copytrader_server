from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

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
    print("✅ Database initialized")

# --------------------------
# POST: Receive trade signal
# --------------------------
@app.route('/api/signal', methods=['POST'])
def receive_signal():
    try:
        # Force JSON parsing even if headers are weird (MT5 sends nonstandard Content-Type)
        data = request.get_json(force=True)
    except Exception as e:
        print(f"❌ Bad JSON: {e}")
        return jsonify({"error": "Bad JSON", "msg": str(e)}), 400

    # Check API key
    if not data or data.get('api_key') != SIGNAL_API_KEY:
        print("❌ Unauthorized access attempt")
        return jsonify({"error": "Unauthorized"}), 401

    # Save signal to DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''
            INSERT INTO signals (symbol, type, volume, sl, tp)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['symbol'], data['type'], data['volume'], data.get('sl', 0), data.get('tp', 0)))
        conn.commit()
        signal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        print(f"✅ Signal #{signal_id} stored: {data['symbol']} {data['type']} {data['volume']}")
        return jsonify({"status": "ok", "id": signal_id}), 200
    except Exception as e:
        print(f"❌ Database error: {e}")
        return jsonify({"error": str(e)}), 500

# --------------------------
# GET: Retrieve new signals
# --------------------------
@app.route('/api/signal/<int:last_id>', methods=['GET'])
def get_signals(last_id):
    try:
        print(f"📥 Client requesting signals after ID: {last_id}")
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT * FROM signals WHERE id > ? ORDER BY id LIMIT 20", (last_id,))
        rows = cur.fetchall()
        conn.close()

        signals = [{
            "id": row[0],
            "symbol": row[1],
            "type": row[2],
            "volume": row[3],
            "sl": row[4] if row[4] else 0,
            "tp": row[5] if row[5] else 0,
            "timestamp": row[6]
        } for row in rows]

        if signals:
            print(f"📤 Sending {len(signals)} signal(s) to client")
        
        return jsonify(signals), 200
        
    except Exception as e:
        print(f"❌ Error retrieving signals: {e}")
        return jsonify({"error": str(e)}), 500

# --------------------------
# GET: Retrieve all signals (for debugging)
# --------------------------
@app.route('/api/signals/all', methods=['GET'])
def get_all_signals():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 50")
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

        return jsonify({
            "total": len(signals),
            "signals": signals
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------------------------
# Health check
# --------------------------
@app.route('/health', methods=['GET'])
def health():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM signals")
        count = cur.fetchone()[0]
        conn.close()
        
        return jsonify({
            "status": "server running",
            "db": "connected",
            "total_signals": count,
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# --------------------------
# Root endpoint
# --------------------------
@app.route('/', methods=['GET'])
def root():
    return jsonify({
        "service": "MT5 Copy Trading Server",
        "version": "1.0",
        "endpoints": {
            "POST /api/signal": "Submit new signal",
            "GET /api/signal/<last_id>": "Get signals after ID",
            "GET /api/signals/all": "Get all signals",
            "GET /health": "Health check"
        }
    }), 200

# --------------------------
# Start Flask app
# --------------------------
if __name__ == '__main__':
    print("🚀 Starting Copy Trading Server...")
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Server will run on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)