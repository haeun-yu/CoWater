FROM python:3.12-slim

WORKDIR /app

COPY services/moth-bridge/requirements.txt services/moth-bridge/requirements.txt
RUN pip install --no-cache-dir -r services/moth-bridge/requirements.txt

COPY shared/ shared/
COPY services/moth-bridge/ services/moth-bridge/

ENV PYTHONPATH=/app

WORKDIR /app/services/moth-bridge

CMD ["python", "main.py"]
