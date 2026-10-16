# CashBridge (SYNTHETIC demo): FastAPI app serving the built React dashboard on port 8000.
# The React bundle ui/web/dist is committed, so no Node is needed in the image.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Seed the deterministic SYNTHETIC inputs. No secrets are baked in; pass LLM_* and OTP_SECRET at run time.
RUN python data/seed_sandbox.py

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
