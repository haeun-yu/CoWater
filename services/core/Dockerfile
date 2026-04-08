FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/core/requirements.txt services/core/requirements.txt
RUN pip install --no-cache-dir -r services/core/requirements.txt

COPY shared/ shared/
COPY services/core/ services/core/

ENV PYTHONPATH=/app

WORKDIR /app/services/core

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
