# Moth Address Diagnostic Implementation Summary

## Your Question
"모든 곳에서 실제로 그 주소를 사용하는게 맞아?" 
(Are all places actually using that address correctly?)

## What I Did
Implemented comprehensive logging in all POCs (01-05) to trace exactly which Moth URL is being used, both at initialization and during heartbeat publishing.

## Changes Made

### 1. Enhanced Initialization Logging (moth_publisher.py initialize method)
Added detailed logging to show:
- All tracks received from Device Registry
- Which code path is selected (track endpoint vs fallback)
- The actual Moth URL being configured
- The heartbeat topic assigned

**Example log output:**
```
Device Registration에서 받은 tracks: 7개
  Track[0]: type=VIDEO, endpoint=/pang/ws/meb?channel=instant&name=69&source=base&track=video
  Track[1]: type=GPS, endpoint=/pang/ws/meb?channel=instant&name=69&source=base&track=gps
  ...
Moth URL (Fallback 엔드포인트): wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base
MothPublisher 초기화 완료
  Moth 서버: wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base
  Heartbeat 토픽: device.heartbeat.69
```

### 2. Enhanced Heartbeat Publishing Logging (moth_publisher.py publish_heartbeat_payload method)
Added logging to show:
- The Moth URL being used when sending each heartbeat
- The channels being published to
- Confirmation of successful publishes

**Example log output:**
```
Heartbeat 발행 (공통채널): Moth=wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base, channel=device.heartbeat, device_id=69
Heartbeat 발행 (전용채널): Moth=wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base, channel=device.heartbeat.69, device_id=69
Heartbeat 발행 완료: device_id=69, topics=[device.heartbeat, device.heartbeat.69]
```

### 3. Test Guide (MOTH_INITIALIZATION_TEST.md)
Created comprehensive test guide with:
- Expected log patterns for each scenario
- Test execution steps with exact commands
- Interpretation guide for different outcomes
- Verification checklist for 5 POCs
- Next steps based on test results

## Files Modified

### POC Transport Modules (moth_publisher.py)
- `pocs/01-usv-lower-agent/transport/moth_publisher.py`
- `pocs/02-auv-lower-agent/transport/moth_publisher.py`
- `pocs/03-rov-lower-agent/transport/moth_publisher.py`
- `pocs/04-usv-middle-agent/transport/moth_publisher.py`
- `pocs/05-control-ship-middle-agent/transport/moth_publisher.py`

### Documentation Created
- `MOTH_INITIALIZATION_TEST.md` - Complete test guide with examples

## How to Use This

### Quick Test
```bash
# Start all POCs with logging
cd /Users/teamgrit/Documents/CoWater/pocs/00-device-registration-server
python -u -m src.api 2>&1 | tee /tmp/poc00.log &
sleep 8

for poc in 01 02 03 04 05; do
  cd "/Users/teamgrit/Documents/CoWater/pocs/${poc}-*"
  python -u device_agent.py 2>&1 | tee /tmp/poc${poc}.log &
  sleep 5
done

# Wait 30 seconds, then check results
sleep 30

# Quick verification
echo "=== MOTH URL STATUS ==="
for log in /tmp/poc0{1..5}.log; do
  poc=$(basename "$log" .log)
  url=$(grep "Moth 서버:" "$log" | head -1)
  echo "POC $poc: $url"
done

# Check heartbeat publishing
echo "=== HEARTBEAT SENDS ==="
for log in /tmp/poc0{1..5}.log; do
  poc=$(basename "$log" .log)
  count=$(grep -c "Heartbeat 발행 완료" "$log" 2>/dev/null || echo 0)
  echo "POC $poc: $count heartbeats sent"
done
```

## What This Reveals

### ✓ If all POCs show:
- Path: "Fallback 엔드포인트"
- URL contains: `name=health_check&source=base&track=base`
- Heartbeat logs appear every ~10 seconds

**Conclusion:** POCs are correctly using the unified address. The issue is in Moth server routing or POC 00 subscriber configuration.

### ⚠️ If some POCs show old parameters:
- Path: "Device Registry 트랙 엔드포인트"
- URL contains: `name={device_id}` or other device-specific values

**Conclusion:** Old device registrations are being used. Restart POCs after POC 00.

### ✗ If heartbeat logs are sparse:
- Check for "Heartbeat 발행 불가" warning logs
- Indicates Moth connection issues

## Key Insight: Two-Path System

The code has two paths for Moth URL selection:

1. **Device Registry Track Endpoint Path** (if available)
   - Uses endpoints provided by Device Registry during registration
   - These endpoints were historically per-track (name=device_id for different tracks)
   - NEW Device Registry now provides `name=health_check` for all endpoints
   - OLD cached data might still show device-specific names

2. **Fallback Path** (if no track endpoint provided)
   - Uses `_build_fallback_pub_endpoint()` function
   - Always returns the unified address with `name=health_check`
   - This is the preferred path after our recent changes

With the new logging, you can see exactly which path each POC is taking and verify they're all using the correct unified parameters.

## Related Documentation

- [MOTH_INITIALIZATION_TEST.md](MOTH_INITIALIZATION_TEST.md) - Detailed test guide
- [SCENARIO_TEST.md](SCENARIO_TEST.md) - Previous test results
- [MOTH_HEARTBEAT_FINAL_STATUS.md](MOTH_HEARTBEAT_FINAL_STATUS.md) - Earlier findings

## Commit Info

- Commit: `1c52653`
- Files modified: 6
- Lines added: 341
- Lines removed: 69
