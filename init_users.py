#!/usr/bin/env python3
"""
Initialisiert Test-User in der Datenbank.

Hinweis: Diese Datei enthielt zuvor fragmentierten Code (Syntaxfehler).
Diese Version ist lauffähig und idempotent. Sie erwartet eine Postgres-URL
in der Umgebungsvariable DATABASE_URL (oder POSTGRES_URL). Passwörter sind
hier im Klartext hinterlegt – bitte für Produktion entfernen!
"""
import os
import sys
try:
    import psycopg2  # type: ignore
except Exception as e:
    print("psycopg2 nicht verfügbar:", e, file=sys.stderr)
    sys.exit(1)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    print("DATABASE_URL/POSTGRES_URL nicht gesetzt – Skript beendet sich ohne Aktion.")
    sys.exit(0)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

# Test-User mit individuellen Passwörtern (nur für Entwicklung!)
users = [
    ("j.hohl@freenet.de", "passjhohl!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin!", "user"),
    ("post@zero2.de", "passzero2!", "user"),
    ("giselapeter@peter-partner.de", "passgisela!", "user"),
    ("stephan@meyer-brehm.de", "passstephan!", "user"),
    ("wolf.hohl@web.de", "passwolfi!", "user"),
    ("geffertj@mac.com", "passjens!", "user"),
    ("geffertkilian@gmail.com", "passkili!", "user"),
    ("levent.graef@posteo.de", "passlevgr!", "user"),
    ("birgit.cook@ulitzka-partner.de", "passbirg!", "user"),
    ("alexander.luckow@icloud.com", "passbirg!", "user"),
    ("frank.beer@kabelmail.de", "passfrab!", "user"),
    ("patrick@silk-relations.com", "passpat!", "user"),
]

for email, password, role in users:
    print(f"Verarbeite: {email}")
    cur.execute(
        """
        INSERT INTO users (email, password_hash, role)
        VALUES (%s, crypt(%s, gen_salt('bf')), %s)
        ON CONFLICT (email)
        DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role
        """,
        (email, password, role),
    )

conn.commit()
cur.close()
conn.close()
print("Alle User erfolgreich angelegt / aktualisiert.")
