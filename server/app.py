import os
import logging
import sqlite3
import secrets
import json
import urllib.request
import urllib.error
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # دعم قواعد البيانات القديمة التي أُنشئت قبل نظام الحسابات.
    columns = [
        row["name"]
        for row in db.execute("PRAGMA table_info(customers)").fetchall()
    ]

    if "user_id" not in columns:
        db.execute("ALTER TABLE customers ADD COLUMN user_id INTEGER")

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


def get_token():
    value = request.headers.get("Authorization", "")
    if value.startswith("Bearer "):
        return value[7:].strip()
    return None


def current_user():
    token = get_token()

    if not token:
        return None

    db = get_db()

    row = db.execute("""
        SELECT users.id, users.username
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
    """, (token,)).fetchone()

    db.close()
    return row


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = current_user()

        if user is None:
            return jsonify({
                "error": "authentication required"
            }), 401

        return func(user, *args, **kwargs)

    return wrapper


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


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if len(username) < 3:
        return jsonify({
            "error": "username must be at least 3 characters"
        }), 400

    if len(password) < 6:
        return jsonify({
            "error": "password must be at least 6 characters"
        }), 400

    password_hash = generate_password_hash(password)

    db = get_db()

    try:
        cursor = db.execute("""
            INSERT INTO users (username, password_hash)
            VALUES (?, ?)
        """, (username, password_hash))

        db.commit()
        user_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        db.close()
        return jsonify({
            "error": "username already exists"
        }), 409

    db.close()

    return jsonify({
        "ok": True,
        "user_id": user_id,
        "username": username
    }), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    db = get_db()

    user = db.execute("""
        SELECT id, username, password_hash
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    if user is None or not check_password_hash(
        user["password_hash"],
        password
    ):
        db.close()
        return jsonify({
            "error": "invalid username or password"
        }), 401

    token = secrets.token_urlsafe(32)

    db.execute("""
        INSERT INTO sessions (token, user_id)
        VALUES (?, ?)
    """, (token, user["id"]))

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "token": token,
        "user_id": user["id"],
        "username": user["username"]
    })


@app.post("/api/logout")
@login_required
def logout(user):
    token = get_token()

    db = get_db()
    db.execute(
        "DELETE FROM sessions WHERE token = ?",
        (token,)
    )
    db.commit()
    db.close()

    return jsonify({"ok": True})


@app.get("/api/me")
@login_required
def me(user):
    return jsonify({
        "id": user["id"],
        "username": user["username"]
    })


@app.get("/api/customers")
@login_required
def customers(user):
    db = get_db()

    rows = db.execute("""
        SELECT id, name, phone, created_at
        FROM customers
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user["id"],)).fetchall()

    db.close()

    return jsonify([dict(row) for row in rows])


@app.post("/api/customers")
@login_required
def add_customer(user):
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()

    if not name:
        return jsonify({
            "error": "name is required"
        }), 400

    db = get_db()

    try:
        cursor = db.execute("""
            INSERT INTO customers (user_id, name, phone)
            VALUES (?, ?, ?)
        """, (user["id"], name, phone or None))

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
@login_required
def get_messages(user):
    customer_id = request.args.get("customer_id", type=int)

    if not customer_id:
        return jsonify({
            "error": "customer_id is required"
        }), 400

    db = get_db()

    customer = db.execute("""
        SELECT id
        FROM customers
        WHERE id = ? AND user_id = ?
    """, (customer_id, user["id"])).fetchone()

    if customer is None:
        db.close()
        return jsonify({
            "error": "customer not found"
        }), 404

    rows = db.execute("""
        SELECT id, customer_id, direction, text, created_at
        FROM messages
        WHERE customer_id = ?
        ORDER BY id ASC
    """, (customer_id,)).fetchall()

    db.close()

    return jsonify([dict(row) for row in rows])


@app.post("/api/messages")
@login_required
def add_message(user):
    data = request.get_json(silent=True) or {}

    customer_id = data.get("customer_id")
    message_text = str(data.get("text", "")).strip()

    if not customer_id or not message_text:
        return jsonify({
            "error": "customer_id and text are required"
        }), 400

    db = get_db()

    customer = db.execute("""
        SELECT id
        FROM customers
        WHERE id = ? AND user_id = ?
    """, (customer_id, user["id"])).fetchone()

    if customer is None:
        db.close()
        return jsonify({
            "error": "customer not found"
        }), 404

    cursor = db.execute("""
        INSERT INTO messages
        (customer_id, direction, text)
        VALUES (?, ?, ?)
    """, (customer_id, "outgoing", message_text))

    db.commit()
    message_id = cursor.lastrowid
    db.close()

    return jsonify({
        "ok": True,
        "message_id": message_id
    }), 201



def whatsapp_configured():
    return all([
        os.environ.get("WHATSAPP_ACCESS_TOKEN"),
        os.environ.get("WHATSAPP_PHONE_NUMBER_ID"),
        os.environ.get("WHATSAPP_API_VERSION")
    ])


@app.post("/api/whatsapp/send")
@login_required
def whatsapp_send(user):
    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    message_text = str(data.get("text", "")).strip()

    if not phone or not message_text:
        return jsonify({
            "error": "phone and text are required"
        }), 400

    if not whatsapp_configured():
        return jsonify({
            "error": "WhatsApp API is not configured"
        }), 503

    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    access_token = os.environ["WHATSAPP_ACCESS_TOKEN"]
    api_version = os.environ["WHATSAPP_API_VERSION"]

    url = (
        f"https://graph.facebook.com/"
        f"{api_version}/{phone_number_id}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")

        logging.error(
            "WhatsApp API error: %s",
            error_body
        )

        return jsonify({
            "error": "WhatsApp API request failed"
        }), e.code

    except Exception:
        logging.exception("WhatsApp API request failed")

        return jsonify({
            "error": "WhatsApp API request failed"
        }), 502

    return jsonify({
        "ok": True,
        "whatsapp": result
    }), 200


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

    logging.info("WhatsApp webhook event received")

    owner_id = os.environ.get("WHATSAPP_OWNER_USER_ID")

    try:
        owner_id = int(owner_id) if owner_id else None
    except ValueError:
        owner_id = None

    if not owner_id:
        logging.warning("WHATSAPP_OWNER_USER_ID is not configured")
        return jsonify({"received": True}), 200

    db = get_db()
    saved = 0

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                for message in value.get("messages", []):
                    sender = str(message.get("from", "")).strip()

                    if not sender:
                        continue

                    message_type = message.get("type")

                    if message_type == "text":
                        text = (
                            message.get("text", {})
                            .get("body", "")
                            .strip()
                        )
                    else:
                        text = f"[WhatsApp message: {message_type}]"

                    if not text:
                        continue

                    customer = db.execute("""
                        SELECT id
                        FROM customers
                        WHERE user_id = ? AND phone = ?
                    """, (owner_id, sender)).fetchone()

                    if customer is None:
                        cursor = db.execute("""
                            INSERT INTO customers
                            (user_id, name, phone)
                            VALUES (?, ?, ?)
                        """, (owner_id, sender, sender))

                        customer_id = cursor.lastrowid
                    else:
                        customer_id = customer["id"]

                    db.execute("""
                        INSERT INTO messages
                        (customer_id, direction, text)
                        VALUES (?, ?, ?)
                    """, (
                        customer_id,
                        "incoming",
                        text
                    ))

                    saved += 1

        db.commit()

    except Exception:
        db.rollback()
        logging.exception("Failed to process WhatsApp webhook")
        db.close()

        return jsonify({
            "received": False,
            "error": "Webhook processing failed"
        }), 500

    db.close()

    return jsonify({
        "received": True,
        "saved_messages": saved
    }), 200


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False
    )
