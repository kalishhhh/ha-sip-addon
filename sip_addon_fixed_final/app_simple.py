#!/usr/bin/env python3

import os
import sys
import logging
import signal
import subprocess
import threading
import time
import shutil
import socket
import pty
from flask import Flask, request, jsonify

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------

SIP_SERVER = os.getenv("SIP_SERVER")
EXTENSION  = os.getenv("EXTENSION")
PASSWORD   = os.getenv("PASSWORD")
SIP_PORT   = int(os.getenv("PORT", 5060))

app = Flask(__name__)

pjsua_process = None
pjsua_running = False
pjsua_cmd = None


# -------------------------------------------------------------------
# Find pjsua
# -------------------------------------------------------------------

def find_pjsua():
    global pjsua_cmd
    for cmd in ["pjsua", "pjsua-cli"]:
        if shutil.which(cmd):
            pjsua_cmd = cmd
            logger.info(f"Found PJSUA at: {shutil.which(cmd)}")
            return True
    logger.error("PJSUA not found")
    return False


# -------------------------------------------------------------------
# Create config
# -------------------------------------------------------------------

def create_config():
    config = (
        f"--id sip:{EXTENSION}@{SIP_SERVER}\n"
        f"--registrar sip:{SIP_SERVER}\n"
        f"--realm *\n"
        f"--username {EXTENSION}\n"
        f"--password {PASSWORD}\n"
        f"--null-audio\n"
        f"--auto-answer 200\n"
        f"--local-port={SIP_PORT}\n"
    )

    with open("/tmp/pjsua.conf", "w") as f:
        f.write(config)

    logger.info("PJSUA config written")


# -------------------------------------------------------------------
# Start pjsua using PTY (REAL FIX)
# -------------------------------------------------------------------

def start_pjsua():
    global pjsua_process, pjsua_running

    if not find_pjsua():
        return False

    create_config()

    logger.info("Starting PJSUA inside PTY...")

    master_fd, slave_fd = pty.openpty()

    pjsua_process = subprocess.Popen(
        [pjsua_cmd, "--config-file=/tmp/pjsua.conf"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True
    )

    pjsua_running = True

    threading.Thread(
        target=read_pty_output,
        args=(master_fd,),
        daemon=True
    ).start()

    time.sleep(3)

    if pjsua_process.poll() is not None:
        logger.error("PJSUA exited immediately")
        return False

    logger.info("PJSUA running successfully")
    return True


def read_pty_output(master_fd):
    while True:
        try:
            output = os.read(master_fd, 1024).decode(errors="ignore")
            if output.strip():
                logger.info(f"PJSUA: {output.strip()}")
        except Exception:
            break


# -------------------------------------------------------------------
# Command sender (write to PTY)
# -------------------------------------------------------------------

def send_command(cmd):
    global pjsua_process
    if not pjsua_running:
        return False
    try:
        pjsua_process.stdin.write((cmd + "\n").encode())
        return True
    except Exception as e:
        logger.error(f"Command failed: {e}")
        return False


# -------------------------------------------------------------------
# API
# -------------------------------------------------------------------

@app.route("/call", methods=["POST"])
def call():
    data = request.get_json(force=True, silent=True) or {}
    dest = data.get("destination")

    if not dest:
        return jsonify({"error": "destination required"}), 400

    command = f"m sip:{dest}@{SIP_SERVER}"
    logger.info(f"Calling {dest}")

    os.write(pjsua_process.stdin.fileno(), (command + "\n").encode())

    return jsonify({"status": "calling"})


@app.route("/hangup", methods=["POST"])
def hangup():
    os.write(pjsua_process.stdin.fileno(), b"h\n")
    return jsonify({"status": "hangup"})


@app.route("/status", methods=["GET"])
def status():
    alive = pjsua_process and pjsua_process.poll() is None
    return jsonify({"running": alive})


# -------------------------------------------------------------------
# Shutdown
# -------------------------------------------------------------------

def shutdown(sig, frame):
    logger.info("Stopping...")
    if pjsua_process:
        pjsua_process.terminate()
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    logger.info("Starting SIP Softphone")

    if not SIP_SERVER or not EXTENSION or not PASSWORD:
        logger.error("Missing SIP config")
        sys.exit(1)

    if not start_pjsua():
        sys.exit(1)

    app.run(host="0.0.0.0", port=8099)


if __name__ == "__main__":
    main()
