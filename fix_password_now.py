# filename: fix_password_now.py
#!/usr/bin/env python3
"""
Minimal robustes Passwort-Reset-Script für Postgres.
Voraussetzungen:
  - pip install psycopg2-binary==2.9.9
  - DATABASE_URL muss gesetzt sein (postgresql://user:pass@host:port/dbname)
Optional:
  - TARGET_EMAIL und NEW_PASSWORD als ENV/Args.
Nutzung:
  python fix_password_now.py [EMAIL] [PASSWORT]
"""
import os
import sys
from typing import Optional

try:
    import psycopg2
except ModuleNotFoundError:
    print("FEHLER: 'psycopg2' fehlt. Bitte installieren: pip install psycopg2-binary==2.9.9", file=sys.stderr)
    sys.exit(1)


def get_args_or_env() -> tuple[str, str, str]:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("FEHLER: DATABASE_URL ist nicht gesetzt.", file=sys.stderr)
        sys.exit(2)

    email: Optional[str] = None
    password: Optional[str] = None

    # Priorität: CLI-Args > ENV > Defaults
    if len(sys.argv) >= 2:
        email = sys.argv[1]
    if len(sys.argv) >= 3:
        password = sys.argv[2]

    email = email or os.getenv("TARGET_EMAIL") or "wolf.hohl@web.de"
    password = password or os.getenv("NEW_PASSWORD") or "test123"

    return db_url, email, password


def main() -> int:
    db_url, email, new_pw = get_args_or_env()

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(dsn=db_url)
        conn.autocommit = False
        cur = conn.cursor()

        # pgcrypto bereitstellen (falls Rechte vorhanden)
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        except Exception as e:
            print(f"Hinweis: 'pgcrypto' konnte nicht installiert werden (evtl. fehlende Rechte): {e}")

        # Passwort aktualisieren (bcrypt via pgcrypto)
        cur.execute(
            """
            UPDATE users
               SET password_hash = crypt(%s, gen_salt('bf'))
             WHERE email = %s
            """,
            (new_pw, email),
        )
        if cur.rowcount == 0:
            print(f"Hinweis: User {email} existiert nicht – lege ihn an …")
            cur.execute(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES (%s, crypt(%s, gen_salt('bf')), 'user')
                """,
                (email, new_pw),
            )
            print(f"✅ User angelegt: {email}")
        else:
            print(f"✅ Passwort aktualisiert für: {email}")

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
    sys.exit(main())
