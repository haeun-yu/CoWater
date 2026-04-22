# PoC 07: Mission Simulator

## Goal

Compose the earlier PoCs into a mission-level demonstration.

## Scenario

```text
1. Control USV starts mission
2. AUV begins survey
3. Sonar contact appears
4. Mine detection event is emitted
5. Operator approves ROV deployment
6. ROV completes neutralization
7. Mission summary is generated
```

## Scope

Included:

- Scenario timeline
- Multi-device parent-child structure
- Network loss and reconnect events
- Mission task progress

Excluded:

- Production autonomy
- Real vehicle commands
- Long-term storage

## Success Criteria

- The same scenario can be replayed deterministically.
- Each mission phase has observable stream/event output.
- Manual approval is represented as an explicit event.
