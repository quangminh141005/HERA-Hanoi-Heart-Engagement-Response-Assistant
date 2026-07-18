FROM python:3.11-slim-bookworm

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

RUN groupadd --gid "${APP_GID}" hera \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home hera

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=hera:hera alembic.ini ./alembic.ini
COPY --chown=hera:hera alembic ./alembic
COPY --chown=hera:hera app ./app
COPY --chown=hera:hera scripts/export_postgres_seed.py scripts/seed_postgres.py scripts/smoke_deploy.py scripts/verify_generated_data.py scripts/verify_model_gateway.py scripts/verify_release_assets.py ./scripts/
COPY --chown=hera:hera data/hera_postgres_seed.json.gz data/hera_postgres_seed.json.gz.sha256 ./data/

USER hera

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
