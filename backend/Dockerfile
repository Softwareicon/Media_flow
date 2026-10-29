# MediaFlow Pro API — production image
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
USER app
EXPOSE 8000
# Migrations run as a separate one-off step (see docs/DEPLOYMENT.md), not on every boot.
# Forwarded headers (client IP, https) are trusted ONLY from FORWARDED_ALLOW_IPS (read natively by
# uvicorn). Set it to your reverse proxy / load balancer address range at deploy time.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--workers", "1"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"
