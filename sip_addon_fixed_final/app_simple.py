#!/usr/bin/env python3
"""
SIP Softphone for Home Assistant
Stable headless version using PJSUA + telnet CLI (no stdin pipe)
"""

import os
import sys
import logging
import signal
import subprocess
import threading
import time
import shutil
import socket
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

SIP_SERVER = os.getenv('SIP_SERVER')
EXTENSION  = os.getenv('EXTENSION')
PASSWORD   = os.getenv('PASSWORD')
SIP_PORT   = int(os.getenv('PORT', 5060))

PJSUA_CLI_PORT = 2323

app = Flask(__name__)

pjsua_process = None
pjsua_running = False
pjsua_cmd = None
watchdog_started = False


# ---------------------------------------------------------------------------
# Find PJSUA
# ---------------------------------------------------------------------------

def find_pjsua():
    global pjsua_cmd
    for cmd in ['pjsua', 'pjsua-cli', 'pjsua2']:
        path = shutil.which(cmd)
        if path:
            pjsua_cmd = cmd
            logger.info(f"Found PJSUA at: {path}")
            return True
    logger.error("PJSUA binary not found!")
    return False


# ---------------------------------------------------------------------------
# Create PJSUA Config (HEADLESS)
# ---------------------------------------------------------------------------

def create_pjsua_config():
    config = (
        f"--id sip:{EXTENSION}@{SIP_SERVER}\n"
        f"--registrar sip:{SIP_SERVER}\n"
        f"--realm *\n"
        f"--username {EXTENSION}\n"
        f"--password {PASSWORD}\n"
        f"--auto-answer 200\n"
        f"--null-audio\n"
        f"--cli-telnet-port={PJSUA_CLI_PORT}\n"
        f"--local-port={SIP_PORT}\n"
    )

    with open('/tmp/pjsua.conf', 'w') as f:
        f.write(config)

    logger.info("PJSUA config created (HEADLESS telnet mode)")


# ---------------------------------------------------------------------------
# Telnet Command Sender
# ---------------------------------------------------------------------------

def send_pjsua_command(command):
    if not pjsua_running:
        logger.error("PJSUA not running")
        return False

    try:
        sock = socket.create_connection(("127.0.0.1", PJSUA_CLI_PORT), timeout=3)

        try:
            sock.recv(4096)
        except Exception:
            pass

        sock.sendall((command + "\r\n").encode())
        time.sleep(0.3)

        try:
            response = sock.recv(4096).decode(errors="replace")
            logger.info(f"PJSUA response: {response.strip()[:200]}")
        except Exception:
            pass

        sock.close()
        return True

    except Exception as e:
        logger.error(f"Telnet command failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Start PJSUA
# ---------------------------------------------------------------------------

def start_pjsua():
    global pjsua_process, pjsua_running, watchdog_started

    if not find_pjsua():
        return False

    create_pjsua_config()

    logger.info("Launching PJSUA...")

    try:
        pjsua_process = subprocess.Popen(
            [pjsua_cmd, '--config-file=/tmp/pjsua.conf'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except Exception as e:
        logger.error(f"Failed to start PJSUA: {e}")
        return False

    threading.Thread(target=_log_output, daemon=True).start()

    # Wait for telnet CLI
    deadline = time.time() + 8
    while time.time() < deadline:
        if pjsua_process.poll() is not None:
            logger.error(f"PJSUA exited immediately with code {pjsua_process.returncode}")
            return False
        if _telnet_ready():
            break
        time.sleep(0.5)
    else:
        logger.error("Telnet CLI did not become ready.")
        return False

    pjsua_running = True
    logger.info("PJSUA is running and ready.")

    if not watchdog_started:
        watchdog_started = True
        threading.Thread(target=_watchdog, daemon=True).start()

    return True


def _telnet_ready():
    try:
        s = socket.create_connection(("127.0.0.1", PJSUA_CLI_PORT), timeout=0.5)
        s.close()
        return True
    except Exception:
        return False


def _log_output():
    for line in iter(pjsua_process.stdout.readline, ''):
        if line.strip():
            logger.info(f"PJSUA: {line.rstrip()}")


def _watchdog():
    global pjsua_running
    while True:
        time.sleep(10)
        if pjsua_process and pjsua_process.poll() is not None:
            logger.warning("PJSUA died — restarting...")
            pjsua_running = False
            time.sleep(5)
            start_pjsua()


def stop_pjsua():
    global pjsua_running
    try:
        send_pjsua_command('q')
        time.sleep(1)
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


def signal_handler(sig, frame):
    logger.info("Shutting down...")
    stop_pjsua()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    alive = pjsua_running and pjsua_process and pjsua_process.poll() is None
    return jsonify({"healthy": alive}), 200 if alive else 503


@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "running": pjsua_running,
        "process_alive": pjsua_process.poll() is None if pjsua_process else False,
        "server": SIP_SERVER,
        "extension": EXTENSION
    })


@app.route('/call', methods=['POST'])
def make_call():
    data = request.get_json(force=True, silent=True) or {}
    destination = data.get("destination")

    if not destination:
        return jsonify({"error": "destination is required"}), 400

    if not pjsua_running:
        return jsonify({"error": "SIP not running"}), 503

    command = f"m sip:{destination}@{SIP_SERVER}"
    logger.info(f"Calling {destination}")

    if send_pjsua_command(command):
        return jsonify({"status": "success"}), 200

    return jsonify({"error": "Failed to initiate call"}), 500


@app.route('/hangup', methods=['POST'])
def hangup():
    if not pjsua_running:
        return jsonify({"error": "SIP not running"}), 503

    if send_pjsua_command("h"):
        return jsonify({"status": "hung up"}), 200

    return jsonify({"error": "Failed to hangup"}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("Starting SIP Softphone...")

    if not SIP_SERVER or not EXTENSION or not PASSWORD:
        logger.error("Missing required env vars")
        sys.exit(1)

    if not start_pjsua():
        logger.error("Failed to start PJSUA")
        sys.exit(1)

    logger.info("SIP Softphone ready. API on port 8099.")
    app.run(host='0.0.0.0', port=8099, debug=False)


if __name__ == "__main__":
    main()
