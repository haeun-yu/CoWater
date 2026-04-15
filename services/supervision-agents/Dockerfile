FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY services/supervision-agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY services/supervision-agents/ ./services/supervision-agents/
COPY shared/ ./shared/

# PYTHONPATH 설정
ENV PYTHONPATH=/app

# Supervision 서비스 실행
CMD ["python", "-m", "uvicorn", "services.supervision_agents.main:app", "--host", "0.0.0.0", "--port", "8001"]
