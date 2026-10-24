#!/usr/bin/env bash
set -e

# Wait for PostgreSQL to become available
echo "Waiting for database connection at ${DATABASE_URL:-localhost:5432}..."

python3 - <<'EOF'
import os
import sys
import time

try:
    import psycopg
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set, skipping wait check.")
        sys.exit(0)
    max_retries = 30
    for i in range(max_retries):
        try:
            with psycopg.connect(db_url, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                print("Database is ready.")
                sys.exit(0)
        except Exception as e:
            if i % 5 == 0:
                print(f"Waiting for database... ({e})")
            time.sleep(1)
    print("Database connection timed out.", file=sys.stderr)
    sys.exit(1)
except ImportError:
    print("psycopg not installed, skipping DB ping check.")
EOF

# Initialize database schema if needed
echo "Applying database schema..."
python3 - <<'EOF'
import os
from backend.db import init_schema
schema_file = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
if os.path.exists(schema_file):
    try:
        init_schema(schema_file)
        print("Schema verified.")
    except Exception as e:
        print(f"Schema init warning: {e}")
EOF

# Seed demo data if SEED_DEMO is true or unset
if [ "${SEED_DEMO:-true}" = "true" ]; then
    echo "Checking demo report seed..."
    python3 scripts/seed_demo.py || echo "Demo seeding skipped or completed."
fi

echo "Starting RepoLens backend on host 0.0.0.0, port 8000..."
exec "$@"
