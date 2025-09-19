import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL not found in environment.")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Starte CREATE EXTENSION pgcrypto ...")
cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
conn.commit()

cur.close()
conn.close()
print("pgcrypto erfolgreich installiert!")
