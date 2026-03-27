#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
exec uvicorn memory_knowledge.server:app \
    --host 0.0.0.0 \
    --port "${SERVER_PORT:-8000}" \
    --timeout-graceful-shutdown 30
