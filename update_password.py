#!/usr/bin/env python3
import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    cur.execute("""
        UPDATE users 
        SET password_hash = crypt('passwolf11!', gen_salt('bf'))
        WHERE email = 'wolf.hohl@web.de'
    """)
    
    conn.commit()
    print("✅ Passwort für wolf.hohl@web.de wurde auf 'passwolf11!' gesetzt")
    cur.close()
    conn.close()
```

### In Railway:
1. Fügen Sie diese Datei zum Backend hinzu
2. Gehen Sie zu Railway → Backend → Settings → Deploy
3. Setzen Sie als "Railway Run Command":
```
   python update_password.py && python -m uvicorn main:app --host 0.0.0.0 --port 8080