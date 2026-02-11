#!/usr/bin/env python3
"""
SIP Softphone for Home Assistant
Uses PJSUA with telnet CLI (port 2323) instead of fragile stdin pipe
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

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Read configuration
SIP_SERVER = os.getenv('SIP_SERVER')
EXTENSION  = os.getenv('EXTENSION')
PASSWORD   = os.getenv('PASSWORD')
SIP_PORT   = int(os.getenv('PORT', 5060))

# Telnet CLI port for PJSUA (internal only)
PJSUA_CLI_PORT = 2323

app = Flask(__name__)

# Globals
pjsua_process  = None
pjsua_running  = False
pjsua_cmd      = None
watchdog_active = False


# ---------------------------------------------------------------------------
# PJSUA binary discovery
# ---------------------------------------------------------------------------

def find_pjsua():
    global pjsua_cmd
    for cmd in ['pjsua', 'pjsua-cli', 'pjsua2']:
        path = shutil.which(cmd)
        if path:
            logger.info(f"Found PJSUA at: {path}")
            pjsua_cmd = cmd
            return True
    for location in ['/usr/bin', '/usr/local/bin', '/opt']:
        try:
            result = subprocess.run(
                ['find', location, '-name', 'pjsua*', '-type', 'f'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                pjsua_cmd = result.stdout.strip().split('\n')[0]
                logger.info(f"Found PJSUA at: {pjsua_cmd}")
                return True
        except Exception:
            pass
    logger.error("PJSUA binary not found!")
    return False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def create_pjsua_config():
    """
    Key change: --use-cli + --cli-telnet-port so PJSUA listens on TCP 2323.
    We do NOT pipe stdin at all — that's what was causing the broken pipe.
    """
    config = (
        f"--id sip:{EXTENSION}@{SIP_SERVER}\n"
        f"--registrar sip:{SIP_SERVER}\n"
        f"--realm *\n"
        f"--username {EXTENSION}\n"
        f"--password {PASSWORD}\n"
        f"--auto-answer 200\n"
        f"--null-audio\n"
        f"--no-vad\n"
        f"--ec-tail 0\n"
        f"--use-cli\n"
        f"--cli-telnet-port {PJSUA_CLI_PORT}\n"  # <-- telnet interface
        f"--port {SIP_PORT}\n"
        f"--log-level 5\n"
        f"--app-log-level 5\n"
        f"--log-file /tmp/pjsua.log\n"           # <-- full log to file
    )
    with open('/tmp/pjsua.conf', 'w') as f:
        f.write(config)
    logger.info("PJSUA config created (telnet CLI on port %d)", PJSUA_CLI_PORT)


# ---------------------------------------------------------------------------
# Telnet command sender
# ---------------------------------------------------------------------------

def send_pjsua_command(command: str, timeout: float = 3.0) -> bool:
    """
    Send a command via telnet to PJSUA's CLI port.
    Much more reliable than writing to stdin.
    """
    if not pjsua_running:
        logger.error("PJSUA not running")
        return False
    try:
        sock = socket.create_connection(('127.0.0.1', PJSUA_CLI_PORT), timeout=timeout)
        # PJSUA telnet CLI sends a prompt first; give it a moment
        time.sleep(0.2)
        sock.recv(4096)  # drain the welcome/prompt
        sock.sendall((command + '\r\n').encode())
        time.sleep(0.3)
        try:
            response = sock.recv(4096).decode(errors='replace')
            logger.info(f"PJSUA response to '{command}': {response.strip()[:200]}")
        except Exception:
            pass
        sock.close()
        return True
    except ConnectionRefusedError:
        logger.error(f"PJSUA telnet port {PJSUA_CLI_PORT} refused — is PJSUA still starting?")
        return False
    except Exception as e:
        logger.error(f"Failed to send command '{command}' to PJSUA: {e}")
        return False


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

def start_pjsua():
    global pjsua_process, pjsua_running

    if not find_pjsua():
        return False

    create_pjsua_config()

    # Kill any leftover PJSUA
    try:
        subprocess.run(['pkill', '-f', 'pjsua'], capture_output=True)
        time.sleep(1)
    except Exception:
        pass

    logger.info(f"Launching PJSUA: {pjsua_cmd} --config-file=/tmp/pjsua.conf")
    try:
        pjsua_process = subprocess.Popen(
            [pjsua_cmd, '--config-file=/tmp/pjsua.conf'],
            stdin=subprocess.DEVNULL,   # <-- NOT a pipe; avoids broken-pipe entirely
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr into stdout
            text=True,
            bufsize=1
        )
    except Exception as e:
        logger.error(f"Failed to launch PJSUA: {e}")
        return False

    # Log all output in background
    threading.Thread(target=_log_pjsua_output, daemon=True).start()

    # Wait up to 8 s for telnet CLI to become available
    logger.info("Waiting for PJSUA telnet CLI to become ready...")
    deadline = time.time() + 8
    while time.time() < deadline:
        if pjsua_process.poll() is not None:
            logger.error(
                f"PJSUA exited immediately (code {pjsua_process.returncode}). "
                f"Check /tmp/pjsua.log for details."
            )
            _dump_pjsua_log()
            return False
        if _telnet_port_open():
            break
        time.sleep(0.5)
    else:
        logger.error("Timed out waiting for PJSUA telnet CLI. Check /tmp/pjsua.log")
        _dump_pjsua_log()
        return False

    pjsua_running = True
    logger.info("PJSUA is ready (telnet CLI up)")

    global watchdog_active
    if not watchdog_active:
        watchdog_active = True
        threading.Thread(target=_watchdog, daemon=True).start()

    return True


def _telnet_port_open() -> bool:
    try:
        s = socket.create_connection(('127.0.0.1', PJSUA_CLI_PORT), timeout=0.5)
        s.close()
        return True
    except Exception:
        return False


def _log_pjsua_output():
    """Stream PJSUA stdout/stderr to our logger."""
    try:
        for line in iter(pjsua_process.stdout.readline, ''):
            if line.strip():
                logger.info(f"PJSUA: {line.rstrip()}")
    except Exception as e:
        logger.debug(f"PJSUA output reader ended: {e}")


def _dump_pjsua_log():
    """Print /tmp/pjsua.log to help diagnose startup failures."""
    try:
        with open('/tmp/pjsua.log') as f:
            content = f.read()
        logger.error(f"=== /tmp/pjsua.log ===\n{content[-3000:]}\n=== end ===")
    except Exception:
        logger.error("Could not read /tmp/pjsua.log")


def _watchdog():
    global pjsua_process, pjsua_running
    logger.info("Watchdog started")
    while True:
        time.sleep(10)
        if pjsua_process and pjsua_process.poll() is not None:
            logger.warning(
                f"PJSUA died (exit {pjsua_process.returncode}), restarting in 5 s..."
            )
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


signal.signal(signal.SIGINT,  signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ---------------------------------------------------------------------------
# Flask API
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    alive = pjsua_running and pjsua_process and pjsua_process.poll() is None
    if alive:
        return jsonify({"status": "healthy", "sip_registered": True}), 200
    return jsonify({"status": "unhealthy", "sip_registered": False}), 503


@app.route('/status', methods=['GET'])
def status():
    process_alive = (pjsua_process.poll() is None) if pjsua_process else False
    return jsonify({
        "registered":    pjsua_running,
        "process_alive": process_alive,
        "server":        SIP_SERVER,
        "extension":     EXTENSION,
        "pjsua_binary":  pjsua_cmd,
        "cli_port":      PJSUA_CLI_PORT,
    }), 200


@app.route('/call', methods=['POST'])
def make_call():
    data = request.get_json(force=True, silent=True) or {}
    destination = data.get('destination')

    if not destination:
        return jsonify({"error": "destination is required"}), 400

    if not pjsua_running:
        return jsonify({"error": "SIP softphone not running"}), 503

    if pjsua_process and pjsua_process.poll() is not None:
        return jsonify({"error": "PJSUA process has died, restart in progress"}), 503

    command = f"m sip:{destination}@{SIP_SERVER}"
    logger.info(f"Initiating call: {command}")

    if send_pjsua_command(command):
        return jsonify({"status": "success", "message": f"Call initiated to {destination}"}), 200
    return jsonify({"error": "Failed to send call command — check container logs"}), 500


@app.route('/hangup', methods=['POST'])
def hangup():
    if not pjsua_running:
        return jsonify({"error": "SIP softphone not running"}), 503
    if send_pjsua_command('h'):
        return jsonify({"status": "success", "message": "Call hung up"}), 200
    return jsonify({"error": "Failed to hangup"}), 500


@app.route('/dtmf', methods=['POST'])
def send_dtmf():
    data = request.get_json(force=True, silent=True) or {}
    digits = data.get('digits')
    if not digits:
        return jsonify({"error": "digits is required"}), 400
    if not pjsua_running:
        return jsonify({"error": "SIP softphone not running"}), 503
    if send_pjsua_command(f"# {digits}"):
        return jsonify({"status": "success", "message": f"DTMF sent: {digits}"}), 200
    return jsonify({"error": "Failed to send DTMF"}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("Starting SIP Softphone...")
    logger.info(f"Server: {SIP_SERVER}  Extension: {EXTENSION}  Port: {SIP_PORT}")

    if not SIP_SERVER or not EXTENSION or not PASSWORD:
        logger.error("Missing required env vars: SIP_SERVER, EXTENSION, PASSWORD")
        sys.exit(1)

    if not start_pjsua():
        logger.error("Failed to start PJSUA — see logs above for the reason")
        sys.exit(1)

    logger.info("SIP Softphone ready. API on port 8099.")
    app.run(host='0.0.0.0', port=8099, debug=False)


if __name__ == '__main__':
    main()