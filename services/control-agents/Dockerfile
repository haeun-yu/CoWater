FROM python:3.12-slim

WORKDIR /app

# shared 패키지와 agents 서비스를 함께 복사
# docker-compose build context: repo root (CoWater/)
COPY shared/ shared/
COPY services/agents/requirements.txt services/agents/requirements.txt

RUN pip install --no-cache-dir -r services/agents/requirements.txt

COPY services/agents/ services/agents/

# shared 패키지를 Python 경로에 추가
ENV PYTHONPATH=/app

WORKDIR /app/services/agents

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
