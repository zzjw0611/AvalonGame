FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 avalon
COPY --chown=avalon:avalon app ./app
COPY --chown=avalon:avalon migrations ./migrations
COPY --chown=avalon:avalon alembic.ini ./alembic.ini
USER avalon
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log --ws-max-size 16384"]
