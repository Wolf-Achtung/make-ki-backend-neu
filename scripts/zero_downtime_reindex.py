#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-Downtime Reindex (per Index, parallel) + REFRESH COLLATION VERSION

Beschreibung
------------
- Reindiziert *benutzerdefinierte* Indizes parallel mit minimalen Locks via
  `REINDEX INDEX CONCURRENTLY`
- Aktualisiert anschließend die Collation-Version der Datenbank:
  `ALTER DATABASE <dbname> REFRESH COLLATION VERSION`
- Nutzt ENV-Variablen zur Steuerung (siehe unten)

Voraussetzungen
---------------
- ENV: DATABASE_URL (postgresql://user:pass@host:port/dbname)
- Paket: psycopg2-binary
- PostgreSQL >= 12 (für CONCURRENTLY)

ENV-Variablen (optional)
------------------------
- WORKERS=4              Anzahl paralleler Reindex-Jobs
- INCLUDE=regex          Nur Indizes, deren Name auf den Regex passt
- EXCLUDE=regex          Indizes ausschließen (Regex)
- DRY_RUN=1              Nur anzeigen, nicht ausführen

Nutzung
-------
  WORKERS=4 python scripts/zero_downtime_reindex.py
"""
from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Tuple

try:
    import psycopg2
except ModuleNotFoundError:
    print("Bitte installieren: pip install psycopg2-binary==2.9.9", file=sys.stderr)
    sys.exit(1)


def get_connection(dsn: str, autocommit: bool = True):
    conn = psycopg2.connect(dsn=dsn)
    conn.autocommit = autocommit  # REINDEX CONCURRENTLY darf nicht in TX-Block
    return conn


def list_user_indexes(dsn: str) -> List[str]:
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


def filter_indexes(indexes: Iterable[str], include: str | None, exclude: str | None) -> List[str]:
    out: List[str] = []
    inc = re.compile(include) if include else None
    exc = re.compile(exclude) if exclude else None
    for idx in indexes:
        if inc and not inc.search(idx):
            continue
        if exc and exc.search(idx):
            continue
        out.append(idx)
    return out


def reindex_index_concurrently(dsn: str, index_name: str, dry_run: bool = False) -> Tuple[str, bool, str]:
    if dry_run:
        return (index_name, True, "DRY_RUN")
    try:
        with get_connection(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(f'REINDEX INDEX CONCURRENTLY "{index_name}";')
        return (index_name, True, "")
    except Exception as e:
        return (index_name, False, f"{type(e).__name__}: {e}")


def refresh_collation_version(dsn: str, dry_run: bool = False) -> Tuple[bool, str]:
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            (dbname,) = cur.fetchone()
    if dry_run:
        return True, "DRY_RUN"
    # ALTER DATABASE darf nicht in einer Transaktion laufen
    try:
        with get_connection(dsn, autocommit=True) as conn2:
            with conn2.cursor() as cur2:
                cur2.execute(f'ALTER DATABASE "{dbname}" REFRESH COLLATION VERSION;')
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        print("FEHLER: DATABASE_URL ist nicht gesetzt.", file=sys.stderr)
        return 2

    workers = int(os.getenv("WORKERS", "4"))
    include = os.getenv("INCLUDE")
    exclude = os.getenv("EXCLUDE")
    dry_run = os.getenv("DRY_RUN", "0") == "1"

    print("[zd-reindex] Indexliste abrufen …")
    all_indexes = list_user_indexes(dsn)
    indexes = filter_indexes(all_indexes, include, exclude)
    print(f"[zd-reindex] Gesamt: {len(all_indexes)} | Nach Filter: {len(indexes)} | Parallel: {workers}")
    if include:
        print(f"[zd-reindex] INCLUDE: {include}")
    if exclude:
        print(f"[zd-reindex] EXCLUDE: {exclude}")
    if not indexes:
        print("[zd-reindex] Keine passenden Indizes – Ende.")
        ok, failed = 0, 0
    else:
        ok = failed = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            fut_map = {ex.submit(reindex_index_concurrently, dsn, idx, dry_run): idx for idx in indexes}
            for fut in as_completed(fut_map):
                idx = fut_map[fut]
                try:
                    name, success, msg = fut.result()
                    if success:
                        ok += 1
                        suffix = f" ({msg})" if msg else ""
                        print(f"  ✅ {name}{suffix}")
                    else:
                        failed += 1
                        print(f"  ❌ {name}: {msg}", file=sys.stderr)
                except Exception as e:
                    failed += 1
                    print(f"  ❌ {idx}: {type(e).__name__}: {e}", file=sys.stderr)

    print(f"[zd-reindex] Ergebnis: OK={ok} | FAIL={failed}")

    print("[zd-reindex] Collation-Version aktualisieren …")
    success, msg = refresh_collation_version(dsn, dry_run=dry_run)
    if success:
        suffix = f" ({msg})" if msg else ""
        print(f"  ✅ REFRESH COLLATION VERSION{suffix}")
        return 0 if failed == 0 else 1
    else:
        print(f"  ❌ REFRESH COLLATION VERSION fehlgeschlagen: {msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
