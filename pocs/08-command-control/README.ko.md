# PoC 08: Command Control

## 목표

운영자 승인, 명령 권한, command event 경로를 검증합니다.

## 범위

포함:

- 텍스트 명령 입력
- Role check
- Dry-run command parsing 후보
- Approval event
- Command event output

제외:

- 음성 인식
- 실제 디바이스 command transport
- 전체 audit database

## 출력

```text
respond.command.{flowId}
command.audit.{commandId}
```

## 성공 기준

- Viewer 권한은 mission state를 변경할 수 없습니다.
- Operator approval은 명시적인 command event를 발행합니다.
- Admin은 agent 또는 mission 설정을 변경할 수 있습니다.

## 실행

```bash
cd pocs/08-command-control
python3 src/command.py --role operator approve rov deploy
python3 src/command.py --role viewer approve rov deploy
python3 src/command.py --role admin agent mine-detector disable
```
