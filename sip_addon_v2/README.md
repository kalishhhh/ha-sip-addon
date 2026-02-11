# SIP Softphone Add-on - S6-Overlay Compatible

## ✅ What's Fixed

**Previous Error:**
```
s6-overlay-suexec: fatal: can only run as pid 1
```

**Root Cause:** 
The Dockerfile had `CMD [ "/run.sh" ]` which bypassed s6-overlay's init system.

**Solution:**
- Removed `CMD` from Dockerfile
- Service script placed in `/etc/services.d/sip_softphone/run`
- s6-overlay automatically starts and manages the service

## 📁 File Structure

```
sip_softphone/
├── config.json
├── build.yaml
├── Dockerfile
├── app_simple.py
└── rootfs/
    └── etc/
        └── services.d/
            └── sip_softphone/
                └── run
```

## 🚀 Installation

### Step 1: Copy to Home Assistant

Copy the entire `sip_addon_v2` folder to:
```
/addons/sip_softphone/
```

**Access methods:**
- **Samba**: `\\homeassistant.local\addons\`
- **SSH**: `/addons/`
- **Terminal**: Copy via SSH/SCP

### Step 2: Reload Add-ons

1. Open Home Assistant
2. Go to **Settings** → **Add-ons**  
3. Click **Add-on Store**
4. Click **⋮** (three dots) → **Reload**

### Step 3: Install

1. Scroll to **Local Add-ons**
2. Click **SIP Softphone**
3. Click **INSTALL**
4. Wait for build (5-10 minutes)

### Step 4: Configure

Click **Configuration** tab:

```yaml
sip_server: "sip.yourprovider.com"
extension: "1000"
password: "your-sip-password"
port: 5060
log_level: "info"
```

Click **SAVE**

### Step 5: Start

1. Click **Info** tab
2. Click **START**
3. Click **Log** tab

**You should see:**
```
✅ Starting SIP Softphone...
✅ SIP Server: sip.yourprovider.com
✅ Extension: 1000
✅ Port: 5060
✅ Starting Python application...
✅ PJSUA started successfully
✅ Starting API server on port 8099...
```

## 📞 Testing

### Test 1: Health Check
```bash
curl http://homeassistant.local:8099/health
```
Expected: `{"status":"healthy","sip_registered":true}`

### Test 2: Make a Call
```bash
curl -X POST http://homeassistant.local:8099/call \
  -H "Content-Type: application/json" \
  -d '{"destination":"1001"}'
```

### Test 3: Hang Up
```bash
curl -X POST http://homeassistant.local:8099/hangup
```

## 🏠 Home Assistant Integration

### Add REST Commands

Edit `configuration.yaml`:

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

Restart Home Assistant.

### Create Automation

```yaml
automation:
  - alias: "Call me when doorbell rings"
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell
        to: "on"
    action:
      - service: rest_command.sip_call
        data:
          destination: "1001"
```

## 🔧 API Reference

All endpoints at `http://localhost:8099/`

| Endpoint | Method | Payload | Description |
|----------|--------|---------|-------------|
| `/health` | GET | - | Health check |
| `/status` | GET | - | Registration status |
| `/call` | POST | `{"destination":"1001"}` | Make call |
| `/hangup` | POST | - | Hang up |
| `/dtmf` | POST | `{"digits":"1234"}` | Send DTMF |

## 🐛 Troubleshooting

### Add-on won't build
- Check internet connection
- Verify Home Assistant can reach ghcr.io
- Check logs for specific errors

### Service won't start
- Verify all configuration fields are filled
- Check SIP credentials are correct
- Enable debug logging: `log_level: "debug"`

### No SIP registration
- Check SIP server address is correct
- Verify port 5060 is not blocked
- Check firewall settings
- Review logs for registration errors

### API not responding
- Ensure addon is started
- Check port 8099 is accessible
- Verify service is running in logs

## 📊 Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `sip_server` | string | required | SIP server address |
| `extension` | string | required | SIP extension/username |
| `password` | password | required | SIP password |
| `port` | int | 5060 | SIP port |
| `log_level` | list | info | debug/info/warning/error |

## ✨ Features

- ✅ Auto-answer incoming calls
- ✅ Make outgoing calls
- ✅ Send DTMF tones
- ✅ REST API control
- ✅ Health monitoring
- ✅ Multi-architecture support
- ✅ Proper s6-overlay integration

## 📝 Notes

- The addon uses PJSUA CLI (stable and reliable)
- API runs on port 8099 (internal)
- SIP runs on port 5060 (configurable)
- Service automatically restarts on failure
- Logs available in Add-on → Log tab

## 🎉 Success!

Your Home Assistant can now make and receive SIP calls!
