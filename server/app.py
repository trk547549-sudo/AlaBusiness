import os
import logging
import sqlite3

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "alabusiness.db")

VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )
    """)

    db.commit()
    db.close()


init_db()


@app.get("/")
def home():
    return send_from_directory(
        os.path.join(BASE_DIR, "..", "web"),
        "index.html"
    )


@app.get("/api/health")
def health():
    return jsonify({
        "app": "Ala Business",
        "status": "online",
        "database": "online",
        "developer": "علاء العمراني"
    })


@app.get("/api/customers")
def customers():
    db = get_db()
    rows = db.execute("""
        SELECT id, name, phone, created_at
        FROM customers
        ORDER BY id DESC
    """).fetchall()
    db.close()

    return jsonify([dict(row) for row in rows])


@app.post("/api/customers")
def add_customer():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()

    if not name:
        return jsonify({
            "error": "name is required"
        }), 400

    db = get_db()

    try:
        cursor = db.execute(
            "INSERT INTO customers (name, phone) VALUES (?, ?)",
            (name, phone or None)
        )
        db.commit()

        customer_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        db.close()
        return jsonify({
            "error": "phone already exists"
        }), 409

    db.close()

    return jsonify({
        "ok": True,
        "customer_id": customer_id
    }), 201


@app.get("/api/messages")
def get_messages():
    customer_id = request.args.get("customer_id", type=int)

    if not customer_id:
        return jsonify({
            "error": "customer_id is required"
        }), 400

    db = get_db()

    rows = db.execute("""
        SELECT id, customer_id, direction, text, created_at
        FROM messages
        WHERE customer_id = ?
        ORDER BY id ASC
    """, (customer_id,)).fetchall()

    db.close()

    return jsonify([dict(row) for row in rows])


@app.post("/api/messages")
def add_message():
    data = request.get_json(silent=True) or {}

    customer_id = data.get("customer_id")
    text = str(data.get("text", "")).strip()

    if not customer_id or not text:
        return jsonify({
            "error": "customer_id and text are required"
        }), 400

    db = get_db()

    customer = db.execute(
        "SELECT id FROM customers WHERE id = ?",
        (customer_id,)
    ).fetchone()

    if customer is None:
        db.close()
        return jsonify({
            "error": "customer not found"
        }), 404

    cursor = db.execute("""
        INSERT INTO messages
        (customer_id, direction, text)
        VALUES (?, ?, ?)
    """, (customer_id, "outgoing", text))

    db.commit()

    message_id = cursor.lastrowid
    db.close()

    return jsonify({
        "ok": True,
        "message_id": message_id
    }), 201


@app.get("/webhook")
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN:
        logging.info("Webhook verification successful")
        return challenge, 200

    logging.warning("Webhook verification failed")
    return "Forbidden", 403


@app.post("/webhook")
def webhook_receive():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            "received": False,
            "error": "Invalid JSON"
        }), 400

    logging.info("Webhook event received: %s", data)

    return jsonify({
        "received": True
    }), 200


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False
    )
