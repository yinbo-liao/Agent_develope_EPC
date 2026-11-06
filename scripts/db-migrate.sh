#!/bin/sh
# =============================================================================
# FPSO EPC — deterministic schema bootstrap / migration runner
#
# Runs inside the one-shot `migrate` Compose service (postgres:16-alpine).
# Applies, in order:
#   1. database/init.sql                     (only when the base schema is absent)
#   2. database/migrations/*.sql sorted by filename (001, 002, 003, ...)
#
# Applied files are recorded in `schema_migrations` so re-runs are no-ops.
# The compose mount exposes the repository's ./database directory at /sql.
#
# Connection settings come from PG* environment variables (PGHOST, PGUSER,
# PGPASSWORD, PGDATABASE) injected by docker-compose.yml.
# =============================================================================
set -eu

SQL_ROOT="${SQL_ROOT:-/sql}"

echo "[migrate] waiting for PostgreSQL at ${PGHOST:-postgres}:${PGPORT:-5432}..."
attempt=0
until pg_isready -q; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        echo "[migrate] ERROR: PostgreSQL did not become ready in 60s" >&2
        exit 1
    fi
    sleep 1
done
echo "[migrate] PostgreSQL is ready."

# Bookkeeping table — also acts as the idempotency marker for every file.
psql -v ON_ERROR_STOP=1 -q -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
        filename    TEXT PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"

is_applied() {
    psql -tA -c "SELECT 1 FROM schema_migrations WHERE filename = '$1'" | grep -qx '1'
}

mark_applied() {
    psql -v ON_ERROR_STOP=1 -q -c \
        "INSERT INTO schema_migrations (filename) VALUES ('$1') ON CONFLICT (filename) DO NOTHING"
}

# --- 1. Base schema -----------------------------------------------------------
# init.sql is not idempotent (plain CREATE TABLE), so only run it when the base
# schema is genuinely missing. An existing volume created by an older compose
# file already has it, and the fresh-volume path goes through this branch too
# because we no longer mount init.sql into /docker-entrypoint-initdb.d.
if is_applied 'init.sql'; then
    echo "[migrate] init.sql already applied — skipping."
elif psql -tA -c "SELECT to_regclass('public.projects')" | grep -q 'projects'; then
    echo "[migrate] base schema already present — recording init.sql."
    mark_applied 'init.sql'
else
    echo "[migrate] applying init.sql..."
    psql -v ON_ERROR_STOP=1 -f "$SQL_ROOT/init.sql"
    mark_applied 'init.sql'
fi

# --- 2. Migrations in deterministic filename order ----------------------------
for file in "$SQL_ROOT"/migrations/*.sql; do
    [ -e "$file" ] || continue
    name="migrations/$(basename "$file")"

    if is_applied "$name"; then
        echo "[migrate] $name already applied — skipping."
        continue
    fi

    echo "[migrate] applying $name..."
    psql -v ON_ERROR_STOP=1 -f "$file"
    mark_applied "$name"
done

echo "[migrate] schema is up to date."
