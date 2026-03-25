FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" appuser

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${SERVER_PORT:-8000}/health || exit 1

CMD ["sh", "-c", "uvicorn memory_knowledge.server:app --host 0.0.0.0 --port ${SERVER_PORT:-8000}"]
