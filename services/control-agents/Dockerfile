FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/control-agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/control-agents/ services/control-agents/

ENV PYTHONPATH=/app

WORKDIR /app/services/control-agents

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
