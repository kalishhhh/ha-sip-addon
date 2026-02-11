# SIP Softphone - Simple Alpine-Based Version

## 🎯 What's Different

This version **completely avoids s6-overlay** by using a simple Alpine Linux base.

**Previous versions failed with:**
- `s6-overlay-suexec: fatal: can only run as pid 1`
- Base image compatibility issues

**This version:**
- ✅ Pure Alpine Linux 3.19
- ✅ No s6-overlay dependency
- ✅ Simple bash startup script
- ✅ Direct Python execution
- ✅ No complex init systems

## 📁 Files

```
sip_softphone/
├── config.json       # Add-on metadata
├── Dockerfile        # Alpine-based, no s6
├── run.sh           # Simple bash script
└── app_simple.py    # Python application
```

## 🚀 Installation

### Step 1: Copy to Home Assistant

Copy the `sip_addon_simple` folder to `/addons/sip_softphone/`

**Methods:**
- **Samba**: `\\homeassistant.local\addons\sip_softphone\`
- **SSH/SCP**: `/addons/sip_softphone/`
- **File Editor**: Use browser

### Step 2: Install

1. Settings → Add-ons → Add-on Store
2. Click ⋮ → Reload
3. Find "SIP Softphone" in Local Add-ons
4. Click INSTALL
5. Wait 5-10 minutes for build

### Step 3: Configure

```yaml
sip_server: "sip.yourprovider.com"
extension: "1000"
password: "your-password"
port: 5060
log_level: "info"
```

### Step 4: Start

Click START and check logs.

**Expected output:**
```
Reading configuration...
Starting SIP Softphone...
SIP Server: sip.yourprovider.com
Extension: 1000
Port: 5060
Log Level: info
Starting Python application...
PJSUA started successfully
Starting API server on port 8099...
```

## 🔧 How It Works

1. **Dockerfile**: Builds from scratch using Alpine Linux
2. **run.sh**: Simple bash script that reads config and starts Python
3. **app_simple.py**: Python Flask app that controls PJSUA CLI
4. **No s6-overlay**: Direct process execution, no init system

## 📞 API Usage

Once running, API is at `http://localhost:8099/`

```bash
# Health check
curl http://localhost:8099/health

# Make call
curl -X POST http://localhost:8099/call \
  -H "Content-Type: application/json" \
  -d '{"destination":"1001"}'

# Hang up
curl -X POST http://localhost:8099/hangup

# Send DTMF
curl -X POST http://localhost:8099/dtmf \
  -H "Content-Type: application/json" \
  -d '{"digits":"1234"}'

# Status
curl http://localhost:8099/status
```

## 🏠 Home Assistant Integration

Add to `configuration.yaml`:

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
```

Use in automations:

```yaml
automation:
  - alias: "Doorbell Call"
    trigger:
      platform: state
      entity_id: binary_sensor.doorbell
      to: "on"
    action:
      service: rest_command.sip_call
      data:
        destination: "1001"
```

## 🐛 Troubleshooting

### Build Fails
- Check internet connection
- Verify Alpine packages are accessible
- Check logs for specific errors

### Won't Start
- Ensure all config fields are filled
- Check SIP credentials
- Enable debug: `log_level: "debug"`

### No Registration
- Verify SIP server address
- Check firewall/network
- Review logs for SIP errors

### API Not Working
- Confirm addon is running
- Check port 8099 accessibility
- Review Python app logs

## ✨ Features

- ✅ Auto-answer incoming calls
- ✅ Make outgoing calls via API
- ✅ Send DTMF tones
- ✅ Health monitoring
- ✅ Multi-architecture support
- ✅ Simple, no complex dependencies
- ✅ Direct process execution

## 📋 Technical Details

**Base Image**: Alpine Linux 3.19  
**Init System**: None (direct execution)  
**SIP Stack**: PJSUA CLI  
**API Framework**: Flask  
**Port**: 8099 (API), 5060 (SIP)  

## 🎉 Why This Should Work

1. No s6-overlay to cause PID issues
2. Simple Alpine base that's well-tested
3. Direct ENTRYPOINT execution
4. Minimal dependencies
5. Standard Home Assistant addon structure

This is the simplest possible working version!
