# PoC 06: Agent Workflow

## 목표

Detection에서 Analysis, Response로 이어지는 이벤트 체인을 검증합니다.

## 범위

포함:

- `detect.* -> analyze.* -> respond.*`
- `flow_id` 전파
- `causation_id` chain
- Alert/Command 후보 생성

제외:

- 디바이스 입력
- 전체 dashboard
- 장기 보고서 저장

## 성공 기준

- 샘플 `detect.mine` event가 analysis 결과를 만듭니다.
- Response 단계가 alert 또는 command recommendation을 만들 수 있습니다.
- 전체 event chain을 `flow_id`로 추적할 수 있습니다.

## 실행

```bash
cd pocs/06-agent-workflow
python3 src/workflow.py --input sample-events/detect-mine.json
```

출력 JSONL:

- `analyze.mine` agent event
- `mine_detected` alert candidate
