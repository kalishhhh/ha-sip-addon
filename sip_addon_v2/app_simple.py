#!/usr/bin/env python3
"""
SIP Softphone for Home Assistant (Simple Version using PJSUA CLI)
Handles incoming and outgoing SIP calls
"""

import os
import sys
import logging
import signal
import subprocess
import threading
import time
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
EXTENSION = os.getenv('EXTENSION')
PASSWORD = os.getenv('PASSWORD')
PORT = int(os.getenv('PORT', 5060))

# Initialize Flask app
app = Flask(__name__)

# Global variables
pjsua_process = None
pjsua_running = False


def create_pjsua_config():
    """Create PJSUA configuration file"""
    config = f"""--id sip:{EXTENSION}@{SIP_SERVER}
--registrar sip:{SIP_SERVER}
--realm *
--username {EXTENSION}
--password {PASSWORD}
--auto-answer 200
--null-audio
--use-cli
--port {PORT}
"""
    
    with open('/tmp/pjsua.conf', 'w') as f:
        f.write(config)
    
    logger.info("PJSUA config created")


def start_pjsua():
    """Start PJSUA process"""
    global pjsua_process, pjsua_running
    
    try:
        create_pjsua_config()
        
        # Start PJSUA with config file
        pjsua_process = subprocess.Popen(
            ['pjsua', '--config-file=/tmp/pjsua.conf'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        pjsua_running = True
        logger.info("PJSUA started successfully")
        
        # Start thread to read PJSUA output
        output_thread = threading.Thread(target=read_pjsua_output, daemon=True)
        output_thread.start()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to start PJSUA: {e}")
        return False


def read_pjsua_output():
    """Read and log PJSUA output"""
    global pjsua_process
    
    if not pjsua_process:
        return
    
    try:
        for line in iter(pjsua_process.stdout.readline, ''):
            if line:
                logger.debug(f"PJSUA: {line.strip()}")
    except Exception as e:
        logger.error(f"Error reading PJSUA output: {e}")


def send_pjsua_command(command):
    """Send command to PJSUA CLI"""
    global pjsua_process
    
    if not pjsua_process or not pjsua_running:
        logger.error("PJSUA not running")
        return False
    
    try:
        pjsua_process.stdin.write(command + '\n')
        pjsua_process.stdin.flush()
        return True
    except Exception as e:
        logger.error(f"Failed to send command to PJSUA: {e}")
        return False


def stop_pjsua():
    """Stop PJSUA process"""
    global pjsua_process, pjsua_running
    
    if pjsua_process:
        try:
            send_pjsua_command('q')
            time.sleep(1)
            pjsua_process.terminate()
            pjsua_process.wait(timeout=5)
            pjsua_running = False
            logger.info("PJSUA stopped")
        except Exception as e:
            logger.error(f"Error stopping PJSUA: {e}")
            pjsua_process.kill()


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down...")
    stop_pjsua()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    if pjsua_running:
        return jsonify({"status": "healthy", "sip_registered": True}), 200
    else:
        return jsonify({"status": "unhealthy", "sip_registered": False}), 503


@app.route('/call', methods=['POST'])
def make_call():
    """Make an outgoing call"""
    try:
        data = request.get_json()
        destination = data.get('destination')
        
        if not destination:
            return jsonify({"error": "destination is required"}), 400
        
        if not pjsua_running:
            return jsonify({"error": "SIP softphone not running"}), 503
        
        # Send make call command to PJSUA
        # Format: m sip:destination@server
        command = f"m sip:{destination}@{SIP_SERVER}"
        
        if send_pjsua_command(command):
            return jsonify({
                "status": "success",
                "message": f"Call initiated to {destination}"
            }), 200
        else:
            return jsonify({"error": "Failed to initiate call"}), 500
            
    except Exception as e:
        logger.error(f"Error making call: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/hangup', methods=['POST'])
def hangup():
    """Hang up active calls"""
    try:
        if not pjsua_running:
            return jsonify({"error": "SIP softphone not running"}), 503
        
        # Send hangup command (h = hangup all)
        if send_pjsua_command('h'):
            return jsonify({"status": "success", "message": "Call hung up"}), 200
        else:
            return jsonify({"error": "Failed to hangup"}), 500
        
    except Exception as e:
        logger.error(f"Error hanging up: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/status', methods=['GET'])
def status():
    """Get softphone status"""
    try:
        return jsonify({
            "registered": pjsua_running,
            "server": SIP_SERVER,
            "extension": EXTENSION
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/dtmf', methods=['POST'])
def send_dtmf():
    """Send DTMF tones"""
    try:
        data = request.get_json()
        digits = data.get('digits')
        
        if not digits:
            return jsonify({"error": "digits is required"}), 400
        
        if not pjsua_running:
            return jsonify({"error": "SIP softphone not running"}), 503
        
        # Send DTMF command
        # Format: # <digits>
        command = f"# {digits}"
        
        if send_pjsua_command(command):
            return jsonify({
                "status": "success",
                "message": f"DTMF sent: {digits}"
            }), 200
        else:
            return jsonify({"error": "Failed to send DTMF"}), 500
            
    except Exception as e:
        logger.error(f"Error sending DTMF: {e}")
        return jsonify({"error": str(e)}), 500


def main():
    """Main function"""
    logger.info("Starting SIP Softphone...")
    logger.info(f"Server: {SIP_SERVER}")
    logger.info(f"Extension: {EXTENSION}")
    logger.info(f"Port: {PORT}")
    
    # Start PJSUA
    if not start_pjsua():
        logger.error("Failed to start SIP softphone")
        sys.exit(1)
    
    logger.info("SIP Softphone started successfully")
    
    # Start Flask web server for API
    logger.info("Starting API server on port 8099...")
    app.run(host='0.0.0.0', port=8099, debug=False)


if __name__ == '__main__':
    main()
