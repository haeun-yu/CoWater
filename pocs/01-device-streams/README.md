# PoC 01: Device Streams - Moth Server Simulator

Real-time multi-device simulator streaming data to Moth server (RSSP/WebSocket).

## Goal

Prove that maritime devices can publish multiple independent real-time streams to Moth server, with parent-child device structure and mixed static/dynamic data transmission patterns.

## Scope

Included:

- **6 device types**: Control Center, Control Ship, Ocean Power Tower (static); USV, AUV, ROV (dynamic)
- **Real-time streaming**: WebSocket connection to Moth server (wss://cobot.center:8287)
- **Sensor simulation**: GPS, IMU, sonar, pressure, temperature, camera, lights, magnetometer
- **Configuration-driven**: `config.json` for easy customization
- **Live dashboard**: HTML viewer for monitoring streams (last 10 data points per device)
- **Smart transmission**: Static devices send only on change, dynamic devices stream continuously

Excluded:

- Protocol parsing (NMEA, ROSNav, etc.) - handled by moth-bridge
- Redis/NATS transport - uses Moth WebSocket directly
- Core persistence - data flows to moth-bridge → core
- Detection/response agents - focus is on data generation

## Architecture

### Device Types

**Static Devices** (Position-Only, Change-Triggered):
- Control Center: Fixed shore station
- Control Ship: Mobile command vessel (position drifts over time)
- Ocean Power Tower: Fixed offshore installation

**Dynamic Devices** (Real-Time Sensors, Continuous Streaming):
- USV (Unmanned Surface Vehicle): 2s update intervals + 3 sensors
- AUV (Autonomous Underwater Vehicle): 3s update intervals + 4 sensors
- ROV (Remotely Operated Vehicle): 1s update intervals + 5 sensors

### Data Flow

```
Moth Server (wss://cobot.center:8287)
    ▲
    │ JSON WebSocket frames
    │
MothSimulator (Python)
├─ Static Loop: Control Center, Control Ship, Ocean Power Tower
└─ Dynamic Loop: USV, AUV, ROV (with sensors)
    ▲
    └─ HTML Dashboard (index.html)
       • Device card grid
       • Click to select
       • Live 10-point stream per device
```

## Configuration

Edit `config.json`:

```json
{
  "static_devices": [
    {
      "device_id": "control-center-01",
      "device_type": "control_center",
      "name": "Control Center 01",
      "position": { "latitude": 37.265, "longitude": 127.008, "altitude": 10.0 },
      "transmission_interval": 3600
    }
  ],
  "dynamic_devices": [
    {
      "device_id": "usv-01",
      "device_type": "usv",
      "transmission_interval": 2,
      "start_position": { "latitude": 37.268, "longitude": 127.012, "altitude": 0.5 },
      "movement": {
        "speed_range": [0.5, 3.0],
        "heading_change_max": 15,
        "depth_range": [0.5, 50.0]
      },
      "sensors": [
        { "sensor_id": "usv-gps-01", "sensor_type": "gps" },
        { "sensor_id": "usv-imu-01", "sensor_type": "imu" },
        { "sensor_id": "usv-sonar-01", "sensor_type": "sonar" }
      ]
    }
  ],
  "moth_server": {
    "url": "wss://cobot.center:8287",
    "channel": "instant"
  },
  "registration_server": {
    "enabled": true,
    "url": "http://localhost:8003",
    "secret_key": "server-secret",
    "fallback_on_failure": false
  }
}
```

## Run

### Simulator

```bash
cd pocs/01-device-streams

# Install dependencies
pip install websockets

# Run simulator
python3 src/moth_simulator.py
```

Output:
```
2026-04-23 14:30:22 - MothSimulator - INFO - Connecting to Moth server: wss://cobot.center:8287
2026-04-23 14:30:25 - MothSimulator - INFO - ✓ Connected to Moth server
2026-04-23 14:30:25 - MothSimulator - INFO - 🚀 Starting simulation...
2026-04-23 14:30:26 - MothSimulator - INFO - 📍 Sent static device: Control Center 01
2026-04-23 14:30:26 - MothSimulator - DEBUG - 📡 Sent dynamic device: USV 01
```

### Dashboard

```bash
# Option 1: Direct file
open index.html

# Option 2: Local server (recommended)
python3 -m http.server 8000
# Visit http://localhost:8000
```

**Features**:
- Real-time Moth connection status
- 6 device cards (click to select)
- Live 10-point data stream per device
- Auto-scroll, responsive design

## Success Criteria

- All 6 devices register successfully when `registration_server.enabled = true`
- Static devices transmit only on position change or timeout
- Dynamic devices stream continuously with realistic sensor data
- HTML dashboard receives and displays data in real-time (last 10 per device)
- Configuration-driven: easy to add/modify devices and sensors

If registration fails and `fallback_on_failure` is `false`, the simulator skips publishing for that device instead of silently falling back to the shared track.

## Payload Examples

### Static Device (Control Ship)

```json
{
  "device_id": "control-ship-01",
  "device_type": "control_ship",
  "name": "Control Ship 01",
  "data_type": "position",
  "timestamp": "2026-04-23T14:30:26.123456+00:00",
  "position": {
    "latitude": 37.2701,
    "longitude": 127.0152,
    "altitude": 5.0
  }
}
```

### Dynamic Device (ROV with Sensors)

```json
{
  "device_id": "rov-01",
  "device_type": "rov",
  "name": "ROV 01",
  "timestamp": "2026-04-23T14:30:28.456789+00:00",
  "position": {
    "latitude": 37.2671,
    "longitude": 127.0112,
    "altitude": -48.3
  },
  "motion": {
    "heading": 254.67,
    "speed": 0.82
  },
  "sensors": {
    "rov-camera-01": {
      "type": "hd_camera",
      "resolution": "1080p",
      "fps": 30
    },
    "rov-pressure-01": {
      "type": "pressure",
      "depth_m": 48.3
    }
  }
}
```

## Integration with CoWater

1. Moth Server receives `instant` channel data
2. moth-bridge normalizes to `PlatformReport` schema
3. Redis pub/sub broadcasts to agents
4. core stores in TimescaleDB, WebSocket to frontend
5. Frontend visualizes positions, alerts, trajectories
