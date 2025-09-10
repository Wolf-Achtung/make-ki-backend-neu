# app/routes/admin_migration.py
from fastapi import APIRouter, Header, HTTPException, Query
import os

SQL = r"""
BEGIN;

CREATE TABLE IF NOT EXISTS feedback (
  id BIGSERIAL PRIMARY KEY,
  email TEXT,
  variant TEXT,
  report_version TEXT,
  details JSONB,
  user_agent TEXT,
  ip INET,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE feedback ADD COLUMN IF NOT EXISTS variant TEXT;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS report_version TEXT;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS details JSONB;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS user_agent TEXT;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS ip INET;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_email ON feedback ((LOWER(email)));

COMMIT;
"""

router = APIRouter()

@router.post("/admin/migrate-feedback", summary="Migrate Feedback", tags=["admin"]) 
def migrate_feedback(
    x_migration_token: str | None = Header(None, alias="X-Migration-Token"),
    token: str | None = Query(None, description="Alternative to X-Migration-Token header"),
):
    """Run one-time idempotent migration on the `feedback` table.
    Accepts the token via **X-Migration-Token** header or `?token=...` query param.
    Requires env `MIGRATION_TOKEN` and DB url via `DB_CONN` or `DATABASE_URL`.
    """
    provided = x_migration_token or token
    expected = os.environ.get("MIGRATION_TOKEN")
    if not expected or provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    dsn = os.environ.get("DB_CONN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=500, detail="DB env var missing")

    try:
        try:
            import psycopg  # psycopg3
            using = "psycopg3"
        except Exception:
            import psycopg2 as psycopg  # type: ignore
            using = "psycopg2"

        if using == "psycopg3":
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(SQL)
                    conn.commit()
        else:
            with psycopg.connect(dsn) as conn:
                cur = conn.cursor()
                cur.execute(SQL)
                conn.commit()
                cur.close()

        return {"ok": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration error: {e}")
