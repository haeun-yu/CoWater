# PoC 07: Mission Simulator

## 목표

앞선 PoC들을 임무 수준의 demonstration으로 조립합니다.

## 시나리오

```text
1. Control USV가 임무 시작
2. AUV가 탐색 시작
3. Sonar contact 발생
4. 기뢰 탐지 이벤트 발행
5. 관제사가 ROV 투입 승인
6. ROV가 제거 완료
7. 임무 요약 생성
```

## 범위

포함:

- Scenario timeline
- 멀티 디바이스 parent-child 구조
- 네트워크 손실/재연결 이벤트 후보
- 임무 task progress

제외:

- 운영용 자율 제어
- 실제 차량 명령
- 장기 저장소

## 성공 기준

- 같은 시나리오를 결정적으로 재생할 수 있습니다.
- 각 mission phase가 관측 가능한 stream/event output을 가집니다.
- 수동 승인이 명시적인 event로 표현됩니다.

## 실행

```bash
cd pocs/07-mission-simulator
python3 src/mission.py --scenario scenarios/mine-clearance.json
```

출력은 하나의 `flow_id`를 공유하는 mission event JSONL입니다.
