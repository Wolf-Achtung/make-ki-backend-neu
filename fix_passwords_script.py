#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fixt die Passwort-Hashes für Kompatibilität mit Python's bcrypt
"""

import os
import sys
import psycopg2
from passlib.hash import bcrypt

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL nicht gefunden", file=sys.stderr)
    sys.exit(1)

# User mit ihren Passwörtern
USERS_TO_FIX = [
    ("wolf.hohl@web.de", "passwolf11!"),
    ("bewertung@ki-sicherheit.jetzt", "passadmin11!"),
    # Füge weitere User nach Bedarf hinzu
]

def main():
    print("🔧 Fixe Passwort-Hashes für Python-Kompatibilität...")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    for email, password in USERS_TO_FIX:
        # Generiere Python-kompatiblen bcrypt Hash
        python_hash = bcrypt.hash(password)
        
        # Update in der Datenbank
        cur.execute("""
            UPDATE users 
            SET password_hash = %s
            WHERE email = %s
        """, (python_hash, email))
        
        print(f"✅ {email} - Passwort-Hash aktualisiert")
    
    conn.commit()
    cur.close()
    conn.close()
    
    print("\n✅ Alle Passwörter gefixt!")
    print("Teste jetzt den Login mit:")
    print("  Email: wolf.hohl@web.de")
    print("  Passwort: passwolf11!")

if __name__ == "__main__":
    main()