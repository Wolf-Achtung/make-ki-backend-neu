#!/usr/bin/env python3
import os
import psycopg2
import sys

DATABASE_URL = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Setze ein einfaches, funktionierendes Passwort
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    cur.execute("""
        UPDATE users 
        SET password_hash = crypt('test123', gen_salt('bf'))
        WHERE email = 'wolf.hohl@web.de'
    """)
    
    # Prüfe ob User existiert
    cur.execute("SELECT email FROM users WHERE email = 'wolf.hohl@web.de'")
    result = cur.fetchone()
    
    if result:
        print("✅ Passwort wurde auf 'test123' gesetzt")
    else:
        print("❌ User wolf.hohl@web.de existiert nicht!")
        # User anlegen
        cur.execute("""
            INSERT INTO users (email, password_hash, role)
            VALUES ('wolf.hohl@web.de', crypt('test123', gen_salt('bf')), 'user')
        """)
        print("✅ User angelegt mit Passwort 'test123'")
    
    conn.commit()
    cur.close()
    conn.close()
    print("FERTIG! Login mit: wolf.hohl@web.de / test123")
    
except Exception as e:
    print(f"FEHLER: {e}")
    sys.exit(1)
```

### In Railway:
1. Diese Datei zum Backend hinzufügen
2. Settings → Deploy → Railway Run Command:
```
   python fix_password_now.py && python -m uvicorn main:app --host 0.0.0.0 --port 8080