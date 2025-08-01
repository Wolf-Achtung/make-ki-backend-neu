import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL not found in environment.")

users = [
    # Admin
    ("wolf.hohl@web.de", "admin2025!", "admin"),

    # Test-User mit individuellen Passwörtern
    ("j.hohl@freenet.de", "passjhohl!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin!", "user"),
    ("post@zero2.de", "passzero2!", "user"),
    ("giselaPeter@peter-partner.de", "passgisela!", "user"),
    ("stephan@meyer-brehm.de", "passstephan!", "user"),
    ("test@example.de", "passtest!", "user"),
    ("geffertj@mac.com", "passjens!", "user"),
    ("geffertkilian@gmail.com", "passkili!", "user"),
    ("levent.graef@posteo.de", "passlevgr!", "user"),
    ("birgit.cook@ulitzka-partner.de", "passbirg!", "user"),
    ("alexander.luckow@icloud.com", "passbirg!", "user"),
]

print("Starte Einfügen/Update der User...")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

for email, password, role in users:
    print(f"Verarbeite: {email}")
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
