FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock \
    && useradd --system --uid 10001 --create-home appuser

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser alembic.ini ./alembic.ini

USER 10001:10001
EXPOSE 8765

CMD ["sh", "-ec", "alembic upgrade head && python -m app.db.seed_demo && exec uvicorn app.main:app --host 0.0.0.0 --port 8765 --no-access-log"]
