#!/usr/bin/env python3

import os
import sys
import logging
import subprocess
import threading
import time
import signal
import shutil
import pty
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

SIP_SERVER = os.getenv("SIP_SERVER")
EXTENSION = os.getenv("EXTENSION")
PASSWORD = os.getenv("PASSWORD")
SIP_PORT = int(os.getenv("PORT", 5060))

# --------------------------------------------------
# Globals
# --------------------------------------------------

app = Flask(__name__)

pjsua_process = None
pjsua_running = False
pty_master_fd = None
pjsua_cmd = None

# --------------------------------------------------
# Find PJSUA Binary
# --------------------------------------------------

def find_pjsua():
    global pjsua_cmd

    for cmd in ["pjsua"]:
        path = shutil.which(cmd)
        if path:
            pjsua_cmd = path
            logger.info(f"Found PJSUA at: {path}")
            return True

    logger.error("PJSUA not found in system!")
    return False


# --------------------------------------------------
# Create PJSUA Config
# --------------------------------------------------

def create_config():
    config = f"""
--id sip:{EXTENSION}@{SIP_SERVER}
--registrar sip:{SIP_SERVER}
--realm *
--username {EXTENSION}
--password {PASSWORD}
--local-port {SIP_PORT}
--auto-answer 200
--null-audio
--no-cli
"""

    with open("/tmp/pjsua.conf", "w") as f:
        f.write(config.strip())

    logger.info("PJSUA config created")


# --------------------------------------------------
# Read PTY Output (prevents exit)
# --------------------------------------------------

def read_pty_output(master_fd):
    while True:
        try:
            output = os.read(master_fd, 1024).decode(errors="ignore")
            if output.strip():
                logger.info(f"PJSUA: {output.strip()}")
        except Exception:
            break


# --------------------------------------------------
# Start PJSUA
# --------------------------------------------------

def start_pjsua():
    global pjsua_process, pjsua_running, pty_master_fd

    if not find_pjsua():
        return False

    create_config()

    logger.info("Starting PJSUA in PTY mode...")

    master_fd, slave_fd = pty.openpty()
    pty_master_fd = master_fd

    pjsua_process = subprocess.Popen(
        [pjsua_cmd, "--config-file=/tmp/pjsua.conf"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True
    )

    threading.Thread(
        target=read_pty_output,
        args=(master_fd,),
        daemon=True
    ).start()

    time.sleep(3)

    if pjsua_process.poll() is not None:
        logger.error("PJSUA exited immediately")
        return False

    pjsua_running = True
    logger.info("PJSUA running successfully")
    return True


# --------------------------------------------------
# Stop PJSUA
# --------------------------------------------------

def stop_pjsua():
    global pjsua_running

    try:
        if pty_master_fd:
            os.write(pty_master_fd, b"q\n")
    except Exception:
        pass

    if pjsua_process:
        try:
            pjsua_process.terminate()
            pjsua_process.wait(timeout=5)
        except Exception:
            pjsua_process.kill()

    pjsua_running = False
    logger.info("PJSUA stopped")


# --------------------------------------------------
# Signal Handling
# --------------------------------------------------

def handle_signal(sig, frame):
    logger.info("Shutting down...")
    stop_pjsua()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# --------------------------------------------------
# Flask Routes
# --------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    if pjsua_running and pjsua_process.poll() is None:
        return jsonify({"status": "healthy"}), 200
    return jsonify({"status": "unhealthy"}), 503


@app.route("/call", methods=["POST"])
def call():
    global pty_master_fd

    data = request.get_json(force=True) or {}
    destination = data.get("destination")

    if not destination:
        return jsonify({"error": "destination required"}), 400

    if not pjsua_running:
        return jsonify({"error": "PJSUA not running"}), 503

    command = f"m sip:{destination}@{SIP_SERVER}\n"

    logger.info(f"Calling {destination}")

    try:
        os.write(pty_master_fd, command.encode())
        return jsonify({"status": "calling"}), 200
    except Exception as e:
        logger.error(f"Call failed: {e}")
        return jsonify({"error": "call failed"}), 500


@app.route("/hangup", methods=["POST"])
def hangup():
    global pty_master_fd

    if not pjsua_running:
        return jsonify({"error": "PJSUA not running"}), 503

    try:
        os.write(pty_master_fd, b"h\n")
        return jsonify({"status": "hung up"}), 200
    except Exception:
        return jsonify({"error": "hangup failed"}), 500


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    logger.info("Starting SIP Softphone...")

    if not SIP_SERVER or not EXTENSION or not PASSWORD:
        logger.error("Missing SIP_SERVER, EXTENSION or PASSWORD")
        sys.exit(1)

    if not start_pjsua():
        logger.error("Failed to start PJSUA")
        sys.exit(1)

    logger.info("API running on port 8099")
    app.run(host="0.0.0.0", port=8099)


if __name__ == "__main__":
    main()
