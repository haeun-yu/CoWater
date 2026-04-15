FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY services/detection-agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY services/detection-agents/ ./services/detection-agents/
COPY shared/ ./shared/

# PYTHONPATH 설정 (shared 패키지 참조)
ENV PYTHONPATH=/app

# Detection 서비스 실행
CMD ["python", "-m", "uvicorn", "services.detection_agents.main:app", "--host", "0.0.0.0", "--port", "8001"]
