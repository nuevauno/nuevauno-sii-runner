FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY src /app/src

ENV PYTHONPATH=/app/src \
    RUNNER_DATA_ROOT=/data/kodo-sii \
    RUNNER_HEADLESS=true \
    RUNNER_TIMEOUT_MS=30000 \
    RUNNER_MAX_WORKERS=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)"

CMD ["uvicorn", "sii_runner.main:app", "--host", "0.0.0.0", "--port", "8080"]
