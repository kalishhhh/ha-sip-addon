#!/usr/bin/env python3

import os
import sys
import socket
import logging
from flask import Flask, request, jsonify

# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --------------------------------------------------
# Environment Variables
# --------------------------------------------------

ASTERISK_HOST = os.getenv("ASTERISK_HOST")
ASTERISK_PORT = int(os.getenv("ASTERISK_PORT", 5038))
AMI_USER = os.getenv("AMI_USER")
AMI_SECRET = os.getenv("AMI_SECRET")

CALLER_EXTENSION = os.getenv("CALLER_EXTENSION")  # e.g. 1023
CONTEXT = os.getenv("ASTERISK_CONTEXT", "from-internal")

app = Flask(__name__)

# --------------------------------------------------
# AMI Helper
# --------------------------------------------------

def send_ami_action(action_lines):
    try:
        s = socket.create_connection((ASTERISK_HOST, ASTERISK_PORT), timeout=5)

        # Read AMI banner
        s.recv(1024)

        # Login
        login_action = (
            f"Action: Login\r\n"
            f"Username: {AMI_USER}\r\n"
            f"Secret: {AMI_SECRET}\r\n"
            f"\r\n"
        )
        s.sendall(login_action.encode())
        s.recv(1024)

        # Send requested action
        s.sendall(action_lines.encode())
        response = s.recv(4096).decode(errors="ignore")

        # Logoff
        s.sendall(b"Action: Logoff\r\n\r\n")
        s.close()

        logger.info(f"AMI response: {response.strip()}")
        return True

    except Exception as e:
        logger.error(f"AMI connection failed: {e}")
        return False


# --------------------------------------------------
# Call Endpoint (Click-to-Call)
# --------------------------------------------------

@app.route("/call", methods=["POST"])
def make_call():
    data = request.get_json(force=True) or {}
    number = data.get("destination")

    if not number:
        return jsonify({"error": "destination required"}), 400

    logger.info(f"Initiating call to {number}")

    originate_action = (
        f"Action: Originate\r\n"
        f"Channel: PJSIP/{CALLER_EXTENSION}\r\n"
        f"Context: {CONTEXT}\r\n"
        f"Exten: {number}\r\n"
        f"Priority: 1\r\n"
        f"CallerID: HomeAssistant\r\n"
        f"Async: true\r\n"
        f"\r\n"
    )

    success = send_ami_action(originate_action)

    if success:
        return jsonify({"status": "calling"}), 200
    return jsonify({"error": "AMI call failed"}), 500


# --------------------------------------------------
# Hangup Endpoint
# --------------------------------------------------

@app.route("/hangup", methods=["POST"])
def hangup():
    # This hangs up all active channels of CALLER_EXTENSION
    hangup_action = (
        f"Action: Hangup\r\n"
        f"Channel: PJSIP/{CALLER_EXTENSION}\r\n"
        f"\r\n"
    )

    success = send_ami_action(hangup_action)

    if success:
        return jsonify({"status": "hangup sent"}), 200
    return jsonify({"error": "hangup failed"}), 500


# --------------------------------------------------
# Status
# --------------------------------------------------

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "running"}), 200


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    if not all([ASTERISK_HOST, AMI_USER, AMI_SECRET, CALLER_EXTENSION]):
        logger.error("Missing required environment variables")
        sys.exit(1)

    logger.info("Starting AMI Softphone Backend")
    app.run(host="0.0.0.0", port=8099)


if __name__ == "__main__":
    main()
