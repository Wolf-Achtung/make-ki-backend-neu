import psycopg2
import os
# .env optional laden (lokal), auf Railway kommen Vars aus dem Environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_PUBLIC_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set")

users = [
    # Admin
    ("bewertung@ki-sicherheit.jetzt", "admin2025!", "admin"),

    # Test-User mit individuellen Passwörtern
    ("j.hohl@freenet.de", "passjhohl!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin!", "user"),
    ("post@zero2.de", "passzero2!", "user"),
    ("giselapeter@peter-partner.de", "passgisela!", "user"),
    ("stephan@meyer-brehm.de", "passstephan!", "user"),
    ("wolf.hohl@web.de", "passwolf!", "user"),
    ("geffertj@mac.com", "passjens!", "user"),
    ("geffertkilian@gmail.com", "passkili!", "user"),
    ("levent.graef@posteo.de", "passlevgr!", "user"),
    ("birgit.cook@ulitzka-partner.de", "passbirg!", "user"),
    ("alexander.luckow@icloud.com", "passbirg!", "user"),
    ("frank.beer@kabelmail.de", "passfrab!", "user"),
    ("patrick@silk-relations.com", "passpat!", "user"),
    ("marc@trailerhaus-onair.de", "passmarct!", "user"),
    ("norbert@trailerhaus.de", "passgis2r!", "user"),
    ("sonia-souto@mac.com", "pass-son!", "user"),
    ("christian.ulitzka@ulitzka-partner.de", "pass2rigz!", "user"),
    ("srack@gmx.net", "pass2rack!", "user"),
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
