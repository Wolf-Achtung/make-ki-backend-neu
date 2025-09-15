#!/usr/bin/env python3
"""
Idempotente DB-Initialisierung für KI-Readiness

- Legt pgcrypto nur an, wenn nicht vorhanden
- Fügt UNIQUE-Constraint für users.email nur hinzu, wenn er fehlt
- Führt optional init_users.py aus (falls vorhanden)

Steuerung: Der Docker-Entrypoint startet dieses Script nur,
wenn RUN_DB_INIT=true gesetzt ist.
"""

import os
import sys
import subprocess
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")

def log(msg: str):
    print(msg, flush=True)

def main() -> int:
    if not DATABASE_URL:
        log("❌ DATABASE_URL fehlt – Initialisierung abgebrochen.")
        return 1

    log("🚀 Starte vollständige DB-Initialisierung...")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        cur = conn.cursor()

        # 1) Extension pgcrypto (idempotent)
        log("Starte: CREATE EXTENSION IF NOT EXISTS pgcrypto ...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        log("pgcrypto bereit.")

        # 2) UNIQUE-Constraint users.email (idempotent)
        log("Starte: UNIQUE Constraint für users.email hinzufügen (falls fehlend) ...")
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM   pg_constraint
                    WHERE  conname = 'unique_email'
                    AND    conrelid = 'users'::regclass
                ) THEN
                    ALTER TABLE users
                    ADD CONSTRAINT unique_email UNIQUE (email);
                END IF;
            END
            $$;
        """)
        log("Constraint geprüft/angelegt.")

        conn.commit()
        cur.close()
        conn.close()
        log("✅ DB-Grundinitialisierung abgeschlossen.")

    except Exception as e:
        log(f"❌ DB-Fehler: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 1

    # 3) Benutzer-Seed/Update separat, wenn Script vorhanden
    if os.path.exists("init_users.py"):
        log("Starte Einfügen/Update der User (init_users.py) ...")
        try:
            r = subprocess.run([sys.executable, "init_users.py"], check=False)
            if r.returncode == 0:
                log("Alle User erfolgreich angelegt / aktualisiert.")
            else:
                log(f"⚠️ init_users.py meldete Returncode {r.returncode} (siehe Logs).")
        except Exception as e:
            log(f"⚠️ init_users.py konnte nicht ausgeführt werden: {e}")
    else:
        log("ℹ️ init_users.py nicht gefunden – übersprungen.")

    log("✅ DB-Initialisierung fertig!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
