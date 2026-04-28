# Moth Initialization Address Verification Test

## Purpose
Verify that all POCs (01-05) are using the **correct unified Moth address** with `name=health_check` parameter during both **initialization** and **heartbeat publishing**.

## What Changed
Each `moth_publisher.py` in POCs 01-05 now logs detailed information at two critical points:

### 1. During Initialization (initialize method)
- Which code path is being used (Device Registry track endpoint vs fallback)
- The actual Moth URL being configured
- The heartbeat topic being assigned

### 2. During Heartbeat Publishing (publish_heartbeat_payload method)
- The Moth URL being used to send heartbeat messages
- The channels being published to
- Confirmation of successful sends

## Expected Log Output

### Initialization Phase

**Expected initialization logs from each POC:**

```
Device Registration에서 받은 tracks: X개
  Track[0]: type=VIDEO, endpoint=...
  Track[1]: type=GPS, endpoint=/pang/ws/meb?channel=instant&name=69&source=base&track=gps
  ...
```

**Then one of:**

**Option A: Using Fallback (PREFERRED)**
```
Moth URL (Fallback 엔드포인트): wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base
  Fallback endpoint: /pang/ws/meb?channel=instant&name=health_check&source=base&track=base
```

**Option B: Using Device Registry Track Endpoint (OLD DATA)**
```
Moth URL (Device Registry 트랙 엔드포인트): wss://cobot.center:8287/pang/ws/meb?channel=instant&name={device_id}&source=base&track=...
```

**Final initialization log:**
```
MothPublisher 초기화 완료
  Moth 서버: wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base
  Heartbeat 토픽: device.heartbeat.{device_id}
  Telemetry 토픽: X개
```

### Heartbeat Publishing Phase

**Every 10 seconds, you should see:**

```
Heartbeat 발행 (공통채널): Moth=wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base, channel=device.heartbeat, device_id=3
Heartbeat 발행 (전용채널): Moth=wss://cobot.center:8287/pang/ws/meb?channel=instant&name=health_check&source=base&track=base, channel=device.heartbeat.3, device_id=3
Heartbeat 발행 완료: device_id=3, topics=[device.heartbeat, device.heartbeat.3]
```

## How to Run the Test

### 1. Ensure Clean State (Optional)
```bash
# Kill any existing POCs
pkill -f "python -u -m src.api"
pkill -f "device_agent.py"
sleep 2
```

### 2. Start POC 00 (Device Registry Server)
```bash
cd /Users/teamgrit/Documents/CoWater/pocs/00-device-registration-server
python -u -m src.api 2>&1 | tee /tmp/poc00.log &
sleep 8
```

### 3. Start POCs 01-05 (with staggered startup)
```bash
for poc in 01 02 03 04 05; do
  cd "/Users/teamgrit/Documents/CoWater/pocs/${poc}-*"
  python -u device_agent.py 2>&1 | tee /tmp/poc${poc}.log &
  sleep 5
done
```

### 4. Let them run for 20+ seconds, then check logs

### 5. Check Initialization Logs

**Check which path each POC selected:**
```bash
echo "=== INITIALIZATION SUMMARY ==="
for log in /tmp/poc0{1..5}.log; do
  poc=$(basename "$log" .log)
  echo "POC $poc:"
  grep -E "Moth URL \(Fallback|Moth URL \(Device" "$log" | head -1
done
```

**Check if Moth URLs contain the correct health_check parameter:**
```bash
echo "=== MOTH URL VERIFICATION ==="
for log in /tmp/poc0{1..5}.log; do
  poc=$(basename "$log" .log)
  url=$(grep "Moth 서버:" "$log" | head -1 | cut -d: -f2-)
  has_health_check=$(echo "$url" | grep -c "name=health_check")
  echo "POC $poc: $([[ $has_health_check -gt 0 ]] && echo '✓ health_check' || echo '✗ MISSING health_check')"
done
```

### 6. Check Heartbeat Publishing Logs

**View heartbeat send attempts (every 10 seconds):**
```bash
echo "=== HEARTBEAT SENDS (POC 01) ==="
grep "Heartbeat 발행" /tmp/poc01.log | tail -5
```

**Check how many heartbeats each POC sent:**
```bash
echo "=== HEARTBEAT COUNT ==="
for log in /tmp/poc0{1..5}.log; do
  poc=$(basename "$log" .log)
  count=$(grep -c "Heartbeat 발행 완료" "$log")
  echo "POC $poc: $count heartbeats sent"
done
```

## Interpretation Guide

### ✓ All POCs using Fallback with correct parameters
**All logs show:**
- `Moth URL (Fallback 엔드포인트): ... name=health_check ...`
- Heartbeat logs show the correct unified URL
- Heartbeat logs should appear every ~10 seconds

**Conclusion:** POCs are correctly configured. If heartbeats aren't reaching Device Registry, issue is in Moth server routing or POC 00 subscriber configuration.

### ⚠️ Mixed paths or old parameters
**Some logs show:**
- `Moth URL (Device Registry 트랙 엔드포인트): ... name={device_id} ...`

**Explanation:** Old device registrations are being used. Each time Device Registry starts, it generates new registrations with unified parameters. This typically happens if:
1. Old cached device data is being reused (unlikely with fresh start)
2. Device Registry is providing old endpoints (unlikely with current code)

**Solution:** Restart all POCs to force fresh registration with POC 00.

### ✗ Heartbeats not being published frequently
**If heartbeat logs are sparse or missing:**
- POC may have failed to initialize Moth connection
- Check for "Heartbeat 발행 불가" warning logs
- Check Moth connectivity: `grep -i "모스" /tmp/poc01.log`

## Verification Checklist

| Aspect | Expected | Check |
|--------|----------|-------|
| **Initialization** | All POCs use Fallback | `grep "Fallback 엔드포인트" /tmp/poc0{1..5}.log` |
| **Parameters** | All have `name=health_check` | `grep "health_check" /tmp/poc0{1..5}.log` |
| **Heartbeats** | Publishing every ~10 sec | `grep "Heartbeat 발행 완료" /tmp/poc01.log` |
| **Channels** | Both device.heartbeat and device.heartbeat.{id} | `grep "공통채널\|전용채널" /tmp/poc01.log` |
| **POC 00** | Receiving heartbeat subscription ack | `grep "device.heartbeat" /tmp/poc00.log` |

## Key Code Locations

### Initialization Logic (moth_publisher.py lines 159-190)
```python
# Two-path selection:
if track_endpoint:  # Device Registry provided endpoint
    self.moth_url = _join_base_and_endpoint(self.moth_base_url, track_endpoint)
    logger.info(f"Moth URL (Device Registry 트랙 엔드포인트): {self.moth_url}")
else:  # Use fallback
    fallback_endpoint = _build_fallback_pub_endpoint(...)
    self.moth_url = _join_base_and_endpoint(self.moth_base_url, fallback_endpoint)
    logger.info(f"Moth URL (Fallback 엔드포인트): {self.moth_url}")
```

### Fallback Endpoint Builder
```python
def _build_fallback_pub_endpoint(device_id: int | None) -> str:
    return f"/pang/ws/meb?channel=instant&name=health_check&source=base&track=base"
```

### Heartbeat Publishing (moth_publisher.py lines 326-356)
```python
async def publish_heartbeat_payload(self, payload: dict) -> None:
    # Publishes to two channels:
    # 1. device.heartbeat (POC 00 meb subscriber receives this)
    # 2. device.heartbeat.{device_id} (device-specific channel)
    
    await self.ws.send(json.dumps({
        "type": "publish",
        "channel": "device.heartbeat",
        "payload": payload
    }))
    logger.debug(f"Heartbeat 발행 (공통채널): Moth={self.moth_url}, ...")
```

## Next Steps After Test

1. **If all POCs show correct parameters:**
   - Heartbeat issue is downstream (Moth server routing or POC 00 subscriber)
   - Check POC 00 logs for subscriber connection issues
   - Verify Moth server is properly routing published messages to subscribed channels

2. **If some POCs show old parameters:**
   - Kill all POCs and Device Registry
   - Restart Device Registry first
   - Then restart each POC sequentially

3. **If heartbeats are not being published:**
   - Check for Moth connection failures in POC logs
   - Verify network connectivity to wss://cobot.center:8287
   - Check Device Registration response includes heartbeat_topic

## Related Documentation

- Previous status: [SCENARIO_TEST.md](SCENARIO_TEST.md) - Shows Moth heartbeat as known issue
- Previous findings: [MOTH_HEARTBEAT_FINAL_STATUS.md](MOTH_HEARTBEAT_FINAL_STATUS.md)
- Main issue: Heartbeat messages published but not received by subscriber
