# CashBridge (SYNTHETIC demo): FastAPI app serving the built React dashboard on port 8000.
# The React bundle ui/web/dist is committed, so no Node is needed in the image.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Seed the deterministic SYNTHETIC inputs and create a writable runtime folder for the live session.
# No secrets are baked in: pass LLM_* and OTP_SECRET at run time (.env is excluded by .dockerignore).
RUN python data/seed_sandbox.py \
    && useradd --create-home --uid 10001 app \
    && mkdir -p data/runtime \
    && chown -R app:app data/runtime
USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=2)"

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
