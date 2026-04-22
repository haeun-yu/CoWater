FROM python:3.12-slim

WORKDIR /app

COPY services/simulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/simulator/ services/simulator/

ENV PYTHONPATH=/app

WORKDIR /app/services/simulator

CMD ["python", "main.py"]
