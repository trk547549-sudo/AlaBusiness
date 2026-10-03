import os
import logging

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

# لا تضع Access Token الحقيقي هنا.
# ضع رمز التحقق في متغير بيئة.
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")


@app.get("/")
def home():
    return send_from_directory("../web", "index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "app": "Ala Business",
        "status": "online",
        "developer": "علاء العمراني"
    })


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

    # هنا سنعالج رسائل WhatsApp Business لاحقًا.
    return jsonify({
        "received": True
    }), 200


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False
    )
