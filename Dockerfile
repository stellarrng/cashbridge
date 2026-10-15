# CashBridge — container for the deterministic core, its test suite and the
# end-to-end walkthrough.
#
# This image previously ended with
#     RUN python data/seed_sandbox.py || true
#     CMD ["streamlit", "run", "ui/app.py", ...]
# Neither file exists (see README §0). The `|| true` hid the failure at build
# time and the container then exited immediately on start. It now runs what is
# actually built.

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEMO_MODE=true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fail the build if the core is broken, rather than shipping a broken image.
RUN python -m pytest -q

CMD ["python", "demo_walkthrough.py"]
