# PoC 08: Command Control

## Goal

Validate operator approval, command authorization, and command events.

## Scope

Included:

- Text command input
- Role check
- Dry-run command parsing
- Approval event
- Command event output

Excluded:

- Voice recognition
- Real device command transport
- Full audit database

## Output

```text
respond.command.{flowId}
command.audit.{commandId}
```

## Success Criteria

- Viewer commands cannot mutate mission state.
- Operator approval emits an explicit command event.
- Admin can change agent or mission settings.

## Run

```bash
cd pocs/08-command-control
python3 src/command.py --role operator approve rov deploy
python3 src/command.py --role viewer approve rov deploy
python3 src/command.py --role admin agent mine-detector disable
```
