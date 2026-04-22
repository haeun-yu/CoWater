# PoC 09: Report Learning

## 목표

임무 이벤트를 요약하고, 사용자 피드백을 받아 향후 threshold 조정 후보를 만듭니다.

## 범위

포함:

- Event JSONL 기반 incident report
- Mission summary
- False-positive feedback fixture
- Threshold suggestion fixture

제외:

- 운영용 LLM 통합
- 자동 parameter 배포
- 영구 report database

## 성공 기준

- Mission event log가 읽을 수 있는 요약으로 변환됩니다.
- 사용자 피드백을 alert 또는 flow와 연결할 수 있습니다.
- 제안된 parameter 변경은 승인 전까지 pending 상태로 남습니다.

## 실행

```bash
cd pocs/09-report-learning
python3 src/report.py --events sample-data/events.jsonl --feedback sample-data/feedback.json --format markdown
```

출력에는 mission summary와 pending learning suggestion이 포함됩니다.
