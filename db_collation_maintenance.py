#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-off Maintenance Script for Postgres Collation Version Mismatch.

Zweck:
  - Führt REINDEX DATABASE <dbname> aus
  - Führt ALTER DATABASE <dbname> REFRESH COLLATION VERSION aus
  - Zeigt vorher/nachher Status an

WARNUNG:
  - REINDEX DATABASE sperrt die betroffenen Tabellen kurzzeitig. Bitte in einem Wartungsfenster ausführen.

Nutzung:
  python db_collation_maintenance.py
  (verwende ENV: DATABASE_URL)
"""
from __future__ import annotations
import os, sys
try:
    import psycopg2
except ModuleNotFoundError:
    print("Bitte zuerst installieren: pip install psycopg2-binary==2.9.9", file=sys.stderr)
    sys.exit(1)

def main() -> int:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        print("FEHLER: DATABASE_URL ist nicht gesetzt.", file=sys.stderr)
        return 2

    with psycopg2.connect(dsn=dsn) as conn:
        conn.autocommit = True  # ALTER DATABASE darf nicht in einer Transaktion laufen
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            (dbname,) = cur.fetchone()
            print(f"Verbunden mit DB: {dbname}")

            # Vorher: Collation-Versionsstatus pro DB anzeigen (sofern verfügbar)
            try:
                cur.execute("""SELECT datname, datcollversion FROM pg_database WHERE datname = current_database()""")
                row = cur.fetchone()
                if row and len(row) > 1:
                    print(f"Aktuelle Collation-Version (laut Katalog): {row[1]}")
            except Exception as e:
                print(f"Hinweis: Collation-Versionsabfrage nicht verfügbar: {e}")

    # REINDEX kann in Transaktion laufen
    with psycopg2.connect(dsn=dsn) as conn2:
        with conn2.cursor() as cur2:
            cur2.execute("SELECT current_database()")
            (dbname,) = cur2.fetchone()
            print(f"REINDEX DATABASE {dbname} ...")
            cur2.execute(f"REINDEX DATABASE {dbname};")
            conn2.commit()
            print("REINDEX abgeschlossen.")

    # REFRESH COLLATION VERSION (kein Transaction Block)
    with psycopg2.connect(dsn=dsn) as conn3:
        conn3.autocommit = True
        with conn3.cursor() as cur3:
            print(f"ALTER DATABASE {dbname} REFRESH COLLATION VERSION ...")
            cur3.execute(f"ALTER DATABASE {dbname} REFRESH COLLATION VERSION;")
            print("REFRESH COLLATION VERSION abgeschlossen.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
