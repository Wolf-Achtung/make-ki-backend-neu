#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-Downtime Reindex (per Index, parallel) + REFRESH COLLATION VERSION

Zweck
-----
- Behebt Collation-Warnungen ohne "REINDEX DATABASE"-Global-Lock
- Reindiziert alle *benutzerdefinierten* Indizes (Schema != pg_catalog, pg_toast)
- Nutzt REINDEX INDEX CONCURRENTLY (ab PG12) für minimale Locks
- Parallelisiert pro Index (konfigurierbar über WORKERS)
- Führt am Ende: ALTER DATABASE <dbname> REFRESH COLLATION VERSION

Voraussetzungen
---------------
- ENV: DATABASE_URL (postgresql://user:pass@host:port/dbname)
- Paket: psycopg2-binary

Nutzung
-------
  WORKERS=4 python scripts/zero_downtime_reindex.py
"""
from __future__ import annotations
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import psycopg2
except ModuleNotFoundError:
    print("Bitte installieren: pip install psycopg2-binary==2.9.9", file=sys.stderr)
    sys.exit(1)


def get_connection(dsn: str, autocommit: bool = True):
    conn = psycopg2.connect(dsn=dsn)
    conn.autocommit = autocommit  # REINDEX CONCURRENTLY darf nicht in TX-Block
    return conn


def list_user_indexes(dsn: str) -> list[str]:
    sql = """
    SELECT i.relname AS index_name
    FROM pg_class i
    JOIN pg_index ix ON ix.indexrelid = i.oid
    JOIN pg_class t ON ix.indrelid = t.oid
    JOIN pg_namespace nsi ON i.relnamespace = nsi.oid
    JOIN pg_namespace nst ON t.relnamespace = nst.oid
    WHERE i.relkind = 'i'
      AND nst.nspname NOT IN ('pg_catalog', 'pg_toast')
      AND nsi.nspname NOT IN ('pg_catalog', 'pg_toast')
    ORDER BY 1;
    """
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [row[0] for row in cur.fetchall()]


def reindex_index_concurrently(dsn: str, index_name: str) -> tuple[str, bool, str]:
    try:
        with get_connection(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(f'REINDEX INDEX CONCURRENTLY "{index_name}";')
        return (index_name, True, "")
    except Exception as e:
        return (index_name, False, f"{type(e).__name__}: {e}")


def refresh_collation_version(dsn: str) -> None:
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            (dbname,) = cur.fetchone()

    # ALTER DATABASE darf nicht in einer Transaktion laufen
    with get_connection(dsn, autocommit=True) as conn2:
        with conn2.cursor() as cur2:
            cur2.execute(f'ALTER DATABASE "{dbname}" REFRESH COLLATION VERSION;')


def main() -> int:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        print("FEHLER: DATABASE_URL ist nicht gesetzt.", file=sys.stderr)
        return 2

    workers = int(os.getenv("WORKERS", "4"))
    print(f"[zero-downtime] Hole Indexliste …")
    indexes = list_user_indexes(dsn)
    print(f"[zero-downtime] {len(indexes)} benutzerdef. Indexe gefunden. Parallel: {workers}")

    if not indexes:
        print("[zero-downtime] Keine Indexe gefunden – breche ab.")
        return 0

    ok, failed = 0, 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut_map = {ex.submit(reindex_index_concurrently, dsn, idx): idx for idx in indexes}
        for fut in as_completed(fut_map):
            idx = fut_map[fut]
            try:
                name, success, msg = fut.result()
                if success:
                    ok += 1
                    print(f"  ✅ {name}")
                else:
                    failed += 1
                    print(f"  ❌ {name}: {msg}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"  ❌ {idx}: {type(e).__name__}: {e}", file=sys.stderr)

    print(f"[zero-downtime] Reindex abgeschlossen: OK={ok}, FAIL={failed}")

    print("[zero-downtime] Aktualisiere Collation-Version …")
    try:
        refresh_collation_version(dsn)
        print("  ✅ ALTER DATABASE … REFRESH COLLATION VERSION")
    except Exception as e:
        print(f"  ❌ REFRESH COLLATION VERSION fehlgeschlagen: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
