#!/usr/bin/env python3

import os
import sys
import logging
import subprocess
import threading
import time
import signal
import socket
import shutil
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
# Environment
# --------------------------------------------------

SIP_SERVER = os.getenv("SIP_SERVER")
EXTENSION  = os.getenv("EXTENSION")
PASSWORD   = os.getenv("PASSWORD")
SIP_PORT   = int(os.getenv("PORT", 5060))

CLI_PORT = 2323  # Telnet CLI port

app = Flask(__name__)

pjsua_process = None
pjsua_running = False
pjsua_cmd = None


# --------------------------------------------------
# Find PJSUA
# --------------------------------------------------

def find_pjsua():
    global pjsua_cmd
    path = shutil.which("pjsua")
    if path:
        pjsua_cmd = path
        logger.info(f"Found PJSUA at: {path}")
        return True
    logger.error("PJSUA binary not found")
    return False


# --------------------------------------------------
# Create Config
# --------------------------------------------------

def create_config():
    config = f"""
--id sip:{EXTENSION}@{SIP_SERVER}
--registrar sip:{SIP_SERVER}
--realm *
--username {EXTENSION}
--password {PASSWORD}
--local-port {SIP_PORT}
--null-audio
--auto-answer 200
--use-cli
--cli-telnet-port {CLI_PORT}
"""

    with open("/tmp/pjsua.conf", "w") as f:
        f.write(config.strip())

    logger.info("PJSUA config written")


# --------------------------------------------------
# Start PJSUA
# --------------------------------------------------

def start_pjsua():
    global pjsua_process, pjsua_running

    if not find_pjsua():
        return False

    create_config()

    logger.info("Starting PJSUA with telnet CLI...")

    pjsua_process = subprocess.Popen(
        [pjsua_cmd, "--config-file=/tmp/pjsua.conf"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    threading.Thread(target=log_output, daemon=True).start()

    # wait for CLI port to open
    deadline = time.time() + 8
    while time.time() < deadline:
        if check_cli_port():
            pjsua_running = True
            logger.info("PJSUA telnet CLI ready")
            return True
        time.sleep(0.5)

    logger.error("Telnet CLI did not start")
    return False


def log_output():
    for line in iter(pjsua_process.stdout.readline, ''):
        if line.strip():
            logger.info(f"PJSUA: {line.strip()}")


def check_cli_port():
    try:
        s = socket.create_connection(("127.0.0.1", CLI_PORT), timeout=1)
        s.close()
        return True
    except Exception:
        return False


# --------------------------------------------------
# Send Telnet Command
# --------------------------------------------------

def send_cli_command(command):
    try:
        s = socket.create_connection(("127.0.0.1", CLI_PORT), timeout=3)

        # read banner
        time.sleep(0.2)
        try:
            s.recv(4096)
        except:
            pass

        s.sendall((command + "\r\n").encode())
        time.sleep(0.3)

        try:
            response = s.recv(4096).decode(errors="ignore")
            logger.info(f"PJSUA response: {response.strip()}")
        except:
            pass

        s.close()
        return True

    except Exception as e:
        logger.error(f"Failed to send CLI command: {e}")
        return False


# --------------------------------------------------
# API Endpoints
# --------------------------------------------------

@app.route("/call", methods=["POST"])
def call():
    data = request.get_json(force=True) or {}
    number = data.get("destination")

    if not number:
        return jsonify({"error": "destination required"}), 400

    if not pjsua_running:
        return jsonify({"error": "PJSUA not running"}), 503

    logger.info(f"Calling {number}")

    success = send_cli_command(f"m sip:{number}")

    if success:
        return jsonify({"status": "calling"}), 200
    return jsonify({"error": "call failed"}), 500


@app.route("/hangup", methods=["POST"])
def hangup():
    if not pjsua_running:
        return jsonify({"error": "PJSUA not running"}), 503

    success = send_cli_command("h")

    if success:
        return jsonify({"status": "hung up"}), 200
    return jsonify({"error": "hangup failed"}), 500


@app.route("/status", methods=["GET"])
def status():
    alive = pjsua_process and pjsua_process.poll() is None
    return jsonify({
        "running": alive,
        "sip_registered": pjsua_running
    })


# --------------------------------------------------
# Shutdown
# --------------------------------------------------

def shutdown(sig, frame):
    logger.info("Shutting down...")
    try:
        send_cli_command("q")
    except:
        pass
    if pjsua_process:
        pjsua_process.terminate()
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    logger.info("Starting SIP Softphone")

    if not SIP_SERVER or not EXTENSION or not PASSWORD:
        logger.error("Missing SIP configuration")
        sys.exit(1)

    if not start_pjsua():
        logger.error("Failed to start PJSUA")
        sys.exit(1)

    logger.info("API running on port 8099")
    app.run(host="0.0.0.0", port=8099)


if __name__ == "__main__":
    main()
