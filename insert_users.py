import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

users = [
    ("j.hohl@freenet.de", "jh123!", "user"),
    ("kerstin.geffert@gmail.com", "kg456!", "user"),
    ("post@zero2.de", "z2mail789!", "user"),
    ("GiselaPeter@peter-partner.de", "gp321!", "user"),
    ("stephan@meyer-brehm.de", "smb654!", "user"),
    ("test@example.de", "test987!", "user"),
    ("wolf.hohl@web.de", "admin2025!", "admin"),
]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    for email, pw, role in users:
        cur.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (%s, crypt(%s, gen_salt('bf')), %s) "
            "ON CONFLICT (email) DO NOTHING;",
            (email, pw, role)
        )
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Alle User erfolgreich angelegt.")
except Exception as e:
    print("❌ Fehler beim Insert:", e)
