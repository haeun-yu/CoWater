FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY services/report/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY services/report/ ./services/report/
COPY shared/ ./shared/

# PYTHONPATH 설정 (shared 패키지 참조)
ENV PYTHONPATH=/app

# Report 서비스 실행
CMD ["python", "-m", "uvicorn", "services.report.main:app", "--host", "0.0.0.0", "--port", "8001"]
