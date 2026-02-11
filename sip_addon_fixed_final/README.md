# SIP Softphone - PJSUA Fixed Version

## ✅ What's Fixed Now

**Previous Error:**
```
ERROR - Failed to start PJSUA: [Errno 2] No such file or directory: 'pjsua'
```

**Fix Applied:**
1. Added `pjsua` package to Dockerfile
2. Updated app to auto-detect pjsua binary location
3. App now searches for pjsua/pjsua-cli/pjsua2

## 📦 Installation

### Quick Steps:

1. **Extract** the zip file
2. **Rename** folder to `sip_softphone`
3. **Copy** to `/addons/sip_softphone/`
4. **Reload** add-ons in Home Assistant
5. **Install** from Local Add-ons
6. **Configure** and **Start**

### Configuration:

```yaml
sip_server: "192.168.1.61"  # Your SIP server IP
extension: "1008"            # Your extension
password: "your-password"
port: 5060
log_level: "info"
```

## 🔍 What Changed

### Dockerfile:
```dockerfile
# Added pjsua package explicitly
RUN apk add --no-cache \
    pjsua \          # <-- THIS IS NEW!
    pjproject \
    pjproject-dev \
    ...
```

### app_simple.py:
- Added `find_pjsua()` function
- Auto-detects pjsua binary location
- Searches common paths: `/usr/bin`, `/usr/local/bin`, `/opt`
- Tries multiple names: `pjsua`, `pjsua-cli`, `pjsua2`

## 📊 Expected Log Output

```
Reading configuration...
Starting SIP Softphone...
SIP Server: 192.168.1.61
Extension: 1008
Port: 5060
Log Level: info
Starting Python application...
INFO - Starting SIP Softphone...
INFO - Server: 192.168.1.61
INFO - Extension: 1008
INFO - Port: 5060
INFO - Found PJSUA at: /usr/bin/pjsua    <-- SUCCESS!
INFO - PJSUA config created
INFO - Starting PJSUA with command: /usr/bin/pjsua
INFO - PJSUA started successfully
INFO - Starting API server on port 8099...
INFO - Running on http://0.0.0.0:8099
```

## 🧪 Testing

### 1. Check Status
```bash
curl http://homeassistant.local:8099/status
```

Expected response:
```json
{
  "registered": true,
  "server": "192.168.1.61",
  "extension": "1008",
  "pjsua_binary": "/usr/bin/pjsua"
}
```

### 2. Make a Call
```bash
curl -X POST http://homeassistant.local:8099/call \
  -H "Content-Type: application/json" \
  -d '{"destination":"1009"}'
```

### 3. Hang Up
```bash
curl -X POST http://homeassistant.local:8099/hangup
```

### 4. Send DTMF
```bash
curl -X POST http://homeassistant.local:8099/dtmf \
  -H "Content-Type: application/json" \
  -d '{"digits":"1234"}'
```

## 🏠 Home Assistant Integration

### configuration.yaml:
```yaml
rest_command:
  sip_call:
    url: "http://localhost:8099/call"
    method: POST
    content_type: "application/json"
    payload: '{"destination": "{{ destination }}"}'
  
  sip_hangup:
    url: "http://localhost:8099/hangup"
    method: POST
  
  sip_dtmf:
    url: "http://localhost:8099/dtmf"
    method: POST
    content_type: "application/json"
    payload: '{"digits": "{{ digits }}"}'
```

### Example Automation:
```yaml
automation:
  - alias: "Doorbell Call"
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell
        to: "on"
    action:
      - service: rest_command.sip_call
        data:
          destination: "1009"
      - delay: "00:00:30"
      - service: rest_command.sip_hangup
```

## 🐛 Troubleshooting

### Build Fails
- Check internet connection
- Verify Alpine repos are accessible

### PJSUA Still Not Found
- Check logs for "Found PJSUA at:" message
- If missing, the `pjsua` Alpine package may not be available
- Alternative: Use PJSIP Python library (more complex)

### Registration Fails
- Verify SIP server IP is correct
- Check username/password
- Ensure port 5060 is not blocked

### No Audio
- This is expected with `--null-audio` flag
- For real audio, would need ALSA configuration

## ✨ Features

- ✅ SIP registration
- ✅ Auto-answer incoming calls
- ✅ Make outgoing calls
- ✅ Send DTMF tones
- ✅ REST API control
- ✅ Auto-detect PJSUA binary
- ✅ Health monitoring
- ✅ Status endpoint

## 📝 Files Included

```
sip_softphone/
├── config.json       # Add-on configuration
├── Dockerfile        # Includes pjsua package
├── run.sh           # Startup script
└── app_simple.py    # Auto-detects pjsua binary
```

## 🎉 Next Steps

1. Verify addon starts without errors
2. Check `/status` endpoint shows pjsua_binary
3. Test making a call
4. Integrate with Home Assistant automations
5. Create useful scenarios (doorbell, alerts, intercom)

This version should work! The key was adding the `pjsua` Alpine package.
