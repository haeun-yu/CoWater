# CoWater POC Architecture Updates

## Overview
This document describes the design changes made to enable the complete mine removal scenario across all POCs (00-06) with proper hierarchical command propagation and system supervision.

## Key Design Changes

### 1. System Layer Agent Support

**Problem**: POC 06 (System Supervisor) could not register as it had no sensors (empty tracks list).

**Solution**: Modified `device_registry.py` to allow system layer agents to have empty tracks:
```python
is_system_layer = str(request.layer or "").lower() == "system"
if not request.tracks and not is_system_layer:
    raise ValueError("tracks must not be empty")
```

**Impact**: 
- System Supervisor can now register and participate in mission control
- Other system-level services can be added without sensor requirements

### 2. Unified POC Port Configuration

**Problem**: POCs 02-06 used inconsistent port numbers (9121, 9131, 9141, 9151, 9161) instead of the standard sequence.

**Changes**:
```
POC 01: 9111 (USV Lower Agent) ✓
POC 02: 9121 → 9112 (AUV Lower Agent)
POC 03: 9131 → 9113 (ROV Lower Agent)
POC 04: 9141 → 9114 (USV Middle Agent)
POC 05: 9151 → 9115 (Control Ship Middle Agent)
POC 06: 9161 → 9116 (System Supervisor)
```

**Impact**: 
- Standard port sequence for easier deployment and debugging
- Consistent configuration across all environments

### 3. A2A Communication Hierarchy

The system now implements a clear hierarchical command structure:

```
System Supervisor (POC 06)
    ↓ (mission.plan, task.assign)
Control Ship Middle Agent (POC 05)
    ↓ (route_move, hold_position, ...)
Lower Agents (POCs 01-03)
    ├─ USV (POC 01)
    ├─ AUV (POC 02)
    └─ ROV (POC 03)
```

**Key Features**:
- System layer agent can plan and assign missions
- Middle layer agents coordinate lower agents
- Lower agents execute tactical operations
- Commands propagate through A2A endpoints

### 4. Diagnostic Logging Cleanup

Removed temporary file-based diagnostic logging from all POCs:
- Removed `/tmp/poc01_send.txt` writes from moth_publisher
- Removed `/tmp/poc01_trace.txt` writes from runtime.py
- Replaced with proper logger.info() statements

**Impact**: 
- Cleaner application logs
- Proper logging infrastructure in place for future debugging

### 5. Entry Point Standardization

Added `device_agent.py` to POC 06 to match the entry point pattern used by all other POCs:
```python
from pathlib import Path
import sys

poc_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(poc_dir))

from controller.api import run

if __name__ == "__main__":
    run(Path(__file__).resolve().parent / "config.json")
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│         Device Registration Server (POC 00)                 │
│              Port: 9100                                      │
│    ├─ Heartbeat Monitor (Moth subscriber)                   │
│    ├─ Device Registry (SQLite)                              │
│    └─ Assignment Engine                                     │
└──────────┬──────────────────────────────────────────────────┘
           │
    ┌──────┴──────────────────────────────────────────┐
    │           A2A Communication Layer               │
    │     (HTTP commands between agents)              │
    └──────┬──────────────────────────────────────────┘
           │
   ┌───────┴──────────────────────────────────────────────┐
   │                                                       │
┌──▼──────────────────────┐        ┌────────────────────┐ │
│ System Supervisor (POC 06)       │ Moth Server        │ │
│ Port: 9116                       │ wss://cobot.center │ │
│ Layer: system                    │      :8287         │ │
│ Role: Mission Planning           │                    │ │
└──┬──────────────────────┘        └────────────────────┘ │
   │                                                       │
   │ mission.plan, task.assign                           │
   ▼                                                       │
┌──────────────────────────────────────────────────────────┐
│ Control Ship Middle Agent (POC 05)                       │
│ Port: 9115                                               │
│ Layer: middle                                            │
│ Role: Regional Coordination                             │
└──┬───────────────────────────────────────────────────────┘
   │
   │ route_move, hold_position, coordinate_children
   │
   ├──────────────────┬──────────────────┬──────────────────┐
   ▼                  ▼                  ▼                  ▼
┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
│ USV (01)│      │ AUV (02)│      │ ROV (03)│      │USV Mid(04)
│ 9111    │      │ 9112    │      │ 9113    │      │ 9114
│ Lower   │      │ Lower   │      │ Lower   │      │ Middle
└─────────┘      └─────────┘      └─────────┘      └─────────┘
```

## Moth Integration Status

**Current Status**: Heartbeat messages are published from agents but not received by the Device Registration Server.

**Investigation Results**:
- POCs successfully publish heartbeat to Moth server
- Device Registration Server successfully subscribes to Moth meb channel
- **Issue**: Messages published to `/pang/ws/pub` endpoints are not routed to `/pang/ws/meb` subscribers

**Workaround**: A2A communication provides full command control regardless of Moth status

**Next Steps**:
- Verify Moth server routing configuration
- Check if message topic mapping needs adjustment
- Consider alternative telemetry collection mechanism

## File Changes Summary

### Modified Files
- `pocs/00-device-registration-server/src/registry/device_registry.py`
  - Allow empty tracks for system layer agents

- `pocs/01-usv-lower-agent/transport/moth_publisher.py`
  - Enhanced initialization logging

- `pocs/02-06/agent/runtime.py` (02, 03, 04, 05)
  - Removed diagnostic file logging

- `pocs/02-06/config.json` (02, 03, 04, 05, 06)
  - Standardized port numbers

### Added Files
- `pocs/06-system-supervisor-agent/device_agent.py`
  - Entry point for System Supervisor POC

## Testing & Validation

See `SCENARIO_TEST.md` for complete mine removal scenario testing methodology.

## Future Enhancements

1. **Moth Integration Fix**: Resolve heartbeat delivery to registry
2. **Automatic Rebinding**: Implement dynamic parent assignment based on position
3. **Mission Persistence**: Store mission state in database
4. **Real-time Dashboard**: POC 07 dashboard integration with live data
5. **Performance Optimization**: Reduce A2A round-trip times
