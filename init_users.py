#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")
if not DATABASE_URL:
    print("DATABASE_URL/POSTGRES_URL not set", file=sys.stderr)
    sys.exit(1)

users = [
    ("j.hohl@freenet.de", "passjhohl11!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin11!", "user"),
    ("post@zero2.de", "passzero11!", "user"),
    ("giselapeter@peter-partner.de", "passgisela11!", "user"),
    ("stephan@meyer-brehm.de", "passstephan11!", "user"),
    ("wolf.hohl@web.de", "passwolf11!", "user"),
    ("geffertj@mac.com", "passjens11!", "user"),
    ("geffertkilian@gmail.com", "passkili11!", "user"),
    ("levent.graef@posteo.de", "passlevgr11!", "user"),
    ("birgit.cook@ulitzka-partner.de", "passbirg111!", "user"),
    ("alexander.luckow@icloud.com", "passbirg11!", "user"),
    ("frank.beer@kabelmail.de", "passfrab11!", "user"),
    ("patrick@silk-relations.com", "passpat11!", "user"),
    ("marc@trailerhaus-onair.de", "passmarct11!", "user"),
    ("norbert@trailerhaus.de", "passgis2r11!", "user"),
    ("sonia-souto@mac.com", "pass-son11!", "user"),
    ("christian.ulitzka@ulitzka-partner.de", "pass2rigz11!", "user"),
    ("srack@gmx.net", "pass2rack11!", "user"),
    ("buss@maria-hilft.de", "pass2mar11!", "user"),
    ("bewertung@ki-sicherheit.jetzt", "passadmin11!", "admin")
]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
for email, password, role in users:
    print("Verarbeite:", email)
    cur.execute("""
        INSERT INTO users (email, password_hash, role)
        VALUES (%s, crypt(%s, gen_salt('bf')), %s)
        ON CONFLICT (email)
        DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role
    """, (email, password, role))
conn.commit()
cur.close()
conn.close()
print("Alle User erfolgreich angelegt / aktualisiert.")
