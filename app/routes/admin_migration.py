"""
Admin migration endpoint for the KI backend.

This module defines an HTTP endpoint that, when invoked with a valid
migration token, executes a set of idempotent SQL statements on the
`feedback` table. These statements ensure that all required columns
exist and add helpful indexes. It is designed to be enabled only
temporarily via an environment flag (`MIGRATION_ENABLED=true`) and
protected by a shared secret (`MIGRATION_TOKEN`).

The migration will create the feedback table if it doesn't exist and
add the following columns if missing:
  - variant (TEXT)
  - report_version (TEXT)
  - details (JSONB)
  - user_agent (TEXT)
  - ip (TEXT)
  - created_at (TIMESTAMPTZ)

It also creates indexes on `created_at` and a case-insensitive
expression index on the lowercased email. If the database schema is
already up to date, running the migration again is safe.
"""

from fastapi import APIRouter, Request, HTTPException
import os
import psycopg2

router = APIRouter()


@router.post("/admin/migrate-feedback")
async def migrate_feedback(request: Request):
    """
    Run a one-time migration on the feedback table.

    This endpoint expects a header named ``X-Migration-Token`` whose
    value must match the ``MIGRATION_TOKEN`` environment variable. If
    the token matches, a series of SQL statements will be executed to
    create or alter the feedback table. The migration is idempotent;
    running it multiple times has no adverse effects.

    Returns a JSON object ``{"ok": true}`` on success or raises an
    HTTPException on failure.
    """

    # Validate token
    token = request.headers.get("X-Migration-Token") or ""
    expected = os.getenv("MIGRATION_TOKEN", "")
    if not expected or token.strip() != expected:
        # Do not leak whether the token exists
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Choose DSN: prefer DB_CONN, fall back to DATABASE_URL
    dsn = os.getenv("DB_CONN") or os.getenv("DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=500, detail="No database DSN configured")

    # Define SQL commands. Each statement will be executed individually.
    migration_sql = """
        CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            email TEXT,
            variant TEXT,
            report_version TEXT,
            details JSONB,
            user_agent TEXT,
            ip TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS variant TEXT;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS report_version TEXT;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS details JSONB;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS user_agent TEXT;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS ip TEXT;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
        CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at);
        CREATE INDEX IF NOT EXISTS idx_feedback_email ON feedback ((lower(email)));
    """

    try:
        # Connect and execute each statement separately. psycopg2 will
        # automatically commit at context exit (autocommit mode is off by default).
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                for statement in [stmt.strip() for stmt in migration_sql.split(";") if stmt.strip()]:
                    cur.execute(statement)
        return {"ok": True}
    except Exception as e:
        # Wrap any error in an HTTPException for API consumers
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
