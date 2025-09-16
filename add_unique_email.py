import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL not found in environment.")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Starte: UNIQUE Constraint für users.email hinzufügen ...")

try:
    cur.execute("ALTER TABLE users ADD CONSTRAINT unique_email UNIQUE(email);")
    conn.commit()
    print("✅ UNIQUE Constraint erfolgreich hinzugefügt.")
except psycopg2.errors.UniqueViolation as e:
    print("⚠️ UNIQUE-Verletzung:", e)
except psycopg2.errors.DuplicateObject as e:
    print("⚠️ Constraint existiert bereits:", e)
except Exception as e:
    if 'already exists' in str(e):
        print("⚠️ Constraint existiert bereits:", e)
    else:
        print("⚠️ Anderer Fehler:", e)

cur.close()
conn.close()
print("✅ Fertig.")
