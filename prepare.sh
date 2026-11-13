#!/bin/bash
set -e

echo "Running PostgreSQL migrations..."
yoyo \
  -vvv apply \
  --batch /app/migrations/postgres \
  -d "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

echo "Running ClickHouse migrations..."
clickhouse-migrations \
  --log-level INFO \
  --migrations-dir /app/migrations/clickhouse \
  --db-host clickhouse \
  --db-user "${CLICKHOUSE_USER:-default}" \
  --db-password "${CLICKHOUSE_PASSWORD:-}" \
  --db-name "${CLICKHOUSE_DB:-default}"
