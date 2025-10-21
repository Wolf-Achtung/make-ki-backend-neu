#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal robustes Passwort-Reset-Script für Postgres.

Nutzung:
  python fix_password_now.py [EMAIL] [PASSWORT]

ENV-Variablen:
  - DATABASE_URL  (postgresql://user:pass@host:port/db)
  - TARGET_EMAIL  (optional, wenn kein CLI-Arg)
  - NEW_PASSWORD  (optional, wenn kein CLI-Arg)

Abhängigkeiten:
  pip install psycopg2-binary==2.9.9
"""
from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

try:
    import psycopg2
except ModuleNotFoundError:
    print("FEHLER: 'psycopg2' fehlt. Installiere: pip install psycopg2-binary==2.9.9", file=sys.stderr)
    sys.exit(1)

def _get_params() -> Tuple[str, str, str]:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("FEHLER: DATABASE_URL ist nicht gesetzt.", file=sys.stderr)
        sys.exit(2)

    email = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("TARGET_EMAIL") or "wolf.hohl@web.de").strip()
    password = (sys.argv[2] if len(sys.argv) > 2 else os.getenv("NEW_PASSWORD") or "test123")
    return db_url, email, password

def main() -> int:
    db_url, email, new_pw = _get_params()

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(dsn=db_url)
        conn.autocommit = False
        cur = conn.cursor()

        # pgcrypto versuchen (falls Rechte vorhanden)
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        except Exception as e:
            print(f"Hinweis: 'pgcrypto' konnte nicht installiert werden (evtl. fehlende Rechte): {e}")

        # Passwort setzen/aktualisieren
        cur.execute(
            """
            UPDATE users
               SET password_hash = crypt(%s, gen_salt('bf'))
             WHERE email = %s
            """,
            (new_pw, email),
        )
        if cur.rowcount == 0:
            print(f"❌ User {email} existiert nicht – lege ihn an …")
            cur.execute(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES (%s, crypt(%s, gen_salt('bf')), 'user')
                """,
                (email, new_pw),
            )
            print(f"✅ User angelegt: {email}")
        else:
            print("✅ Passwort aktualisiert")

        conn.commit()
        print(f"FERTIG! Login mit: {email} / {new_pw}")
        return 0

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
