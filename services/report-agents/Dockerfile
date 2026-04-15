FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY services/report-agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY services/report-agents/ ./services/report-agents/
COPY shared/ ./shared/

# PYTHONPATH 설정
ENV PYTHONPATH=/app

# Report 서비스 실행
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "/app/services/report-agents", "--host", "0.0.0.0", "--port", "8001"]
