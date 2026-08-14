#!/bin/sh
set -e

echo "Starting backend entrypoint..."

# If DATABASE_URL points to Postgres, wait for it to be ready
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgres"; then
  echo "Detected Postgres DATABASE_URL, waiting for DB to become available..."
  until python - <<PY
import os
from sqlalchemy import create_engine
try:
    create_engine(os.environ['DATABASE_URL']).connect()
    print('db_ok')
except Exception:
    raise SystemExit(1)
PY
  do
    echo "waiting..."
    sleep 1
  done
fi

echo "Running alembic migrations..."
set +e
# If the DB already has tables but no alembic_version, stamp head to avoid duplicate-create errors
python - <<PY
import os
from sqlalchemy import create_engine, inspect
engine = create_engine(os.environ.get('DATABASE_URL'))
inspector = inspect(engine)
has_conversations = 'conversations' in inspector.get_table_names()
if has_conversations:
    print('tables exist; stamping alembic to head')
    raise SystemExit(2)
else:
    print('no existing tables; will run migrations')
    raise SystemExit(3)
PY
RET=$?
set -e
if [ "$RET" -eq 2 ]; then
  alembic -c /app/alembic.ini stamp head
else
  alembic -c /app/alembic.ini upgrade head
fi

echo "Starting Uvicorn"
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000