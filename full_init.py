#!/usr/bin/env python3
"""
Idempotente DB-Initialisierung für KI-Readiness

- Legt pgcrypto nur an, wenn nicht vorhanden
- Fügt UNIQUE-Constraint für users.email nur hinzu, wenn er fehlt
- Führt IMMER init_users.py aus (falls vorhanden)

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
        log("✅ pgcrypto bereit.")

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
        log("✅ Constraint geprüft/angelegt.")

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

    # 3) WICHTIG: Benutzer-Update IMMER ausführen
    log("📝 Suche nach init_users.py für User-Updates...")
    
    # Prüfe verschiedene mögliche Pfade
    possible_paths = [
        "init_users.py",
        "./init_users.py",
        "/app/init_users.py",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_users.py")
    ]
    
    init_users_found = False
    for path in possible_paths:
        if os.path.exists(path):
            init_users_found = True
            log(f"✅ init_users.py gefunden unter: {path}")
            log("Starte Einfügen/Update der User...")
            
            try:
                # Führe init_users.py direkt aus
                result = subprocess.run(
                    [sys.executable, path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.stdout:
                    log(f"Output: {result.stdout}")
                
                if result.stderr:
                    log(f"Fehler/Warnungen: {result.stderr}")
                
                if result.returncode == 0:
                    log("✅ Alle User erfolgreich angelegt/aktualisiert!")
                else:
                    log(f"⚠️ init_users.py meldete Returncode {result.returncode}")
                    # Trotzdem weitermachen, da es ein Update sein könnte
                    
            except Exception as e:
                log(f"⚠️ Fehler beim Ausführen von init_users.py: {e}")
                # Fallback: Direktes Ausführen des User-Updates
                log("Versuche direktes User-Update...")
                try:
                    exec(open(path).read())
                    log("✅ User-Update direkt ausgeführt")
                except Exception as exec_error:
                    log(f"❌ Direktes Update fehlgeschlagen: {exec_error}")
            break
    
    if not init_users_found:
        log("⚠️ init_users.py nicht gefunden!")
        log("📍 Aktuelles Verzeichnis: " + os.getcwd())
        log("📁 Dateien im Verzeichnis: " + str(os.listdir('.')))
        
        # Notfall-Fallback: User direkt hier updaten
        log("🔧 Führe Notfall-User-Update direkt aus...")
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            
            # Mindestens den wichtigsten User updaten
            cur.execute("""
                UPDATE users 
                SET password_hash = crypt('passwolf11!', gen_salt('bf'))
                WHERE email = 'wolf.hohl@web.de'
            """)
            
            affected = cur.rowcount
            if affected > 0:
                log(f"✅ Passwort für wolf.hohl@web.de erfolgreich aktualisiert")
            else:
                log("⚠️ User wolf.hohl@web.de nicht gefunden oder nicht geändert")
            
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            log(f"❌ Notfall-Update fehlgeschlagen: {e}")

    log("✅ DB-Initialisierung komplett abgeschlossen!")
    return 0

if __name__ == "__main__":
    sys.exit(main())