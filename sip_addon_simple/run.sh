#!/bin/bash
set -e

CONFIG_PATH=/data/options.json

echo "Reading configuration..."

# Read configuration using jq
SIP_SERVER=$(jq -r '.sip_server // empty' $CONFIG_PATH)
EXTENSION=$(jq -r '.extension // empty' $CONFIG_PATH)
PASSWORD=$(jq -r '.password // empty' $CONFIG_PATH)
PORT=$(jq -r '.port // 5060' $CONFIG_PATH)
LOG_LEVEL=$(jq -r '.log_level // "info"' $CONFIG_PATH)

# Validate configuration
if [ -z "$SIP_SERVER" ]; then
    echo "ERROR: SIP server is not configured!"
    exit 1
fi

if [ -z "$EXTENSION" ]; then
    echo "ERROR: Extension is not configured!"
    exit 1
fi

if [ -z "$PASSWORD" ]; then
    echo "ERROR: Password is not configured!"
    exit 1
fi

echo "Starting SIP Softphone..."
echo "SIP Server: ${SIP_SERVER}"
echo "Extension: ${EXTENSION}"
echo "Port: ${PORT}"
echo "Log Level: ${LOG_LEVEL}"

# Export configuration
export SIP_SERVER
export EXTENSION
export PASSWORD
export PORT
export LOG_LEVEL

# Start application
cd /app
exec python3 app.py
