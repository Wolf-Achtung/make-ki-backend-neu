#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setzt alle User-Passwörter auf 'test123'
EINMALIG AUSFÜHREN - Danach per Mail informieren
"""

import os
import sys
import psycopg2
from passlib.context import CryptContext

# Passlib Context
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__ident="2b"
)

def main():
    DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL nicht gefunden", file=sys.stderr)
        return 1
    
    print("="*60)
    print("🔧 SETZE ALLE PASSWÖRTER AUF 'test123'")
    print("="*60)
    print()
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()
        
        # Hole alle User
        cur.execute("SELECT email, role FROM users ORDER BY email")
        users = cur.fetchall()
        
        print(f"📊 Gefunden: {len(users)} User")
        print()
        
        # Erstelle bcrypt-Hash für 'test123'
        test_password_hash = pwd_context.hash("test123")
        
        success_count = 0
        
        for email, role in users:
            try:
                cur.execute("""
                    UPDATE users 
                    SET password_hash = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE email = %s
                """, (test_password_hash, email))
                
                print(f"  ✅ {email} ({role})")
                success_count += 1
                
            except Exception as e:
                print(f"  ❌ {email}: {e}")
        
        # Commit
        conn.commit()
        
        print()
        print("="*60)
        print(f"✅ {success_count} Passwörter auf 'test123' gesetzt")
        print("="*60)
        print()
        print("📧 JETZT: E-Mail an alle User senden mit:")
        print()
        print("   Login-URL: https://make.ki-sicherheit.jetzt/login")
        print("   Passwort: test123")
        print()
        print("⚠️  WICHTIG: User müssen nach Login Passwort ändern!")
        print()
        
        # Liste alle E-Mails für Copy-Paste
        print("📋 E-Mail-Adressen (für BCC):")
        print("-" * 60)
        for email, _ in users:
            print(f"   {email}")
        print()
        
        cur.close()
        conn.close()
        return 0
        
    except Exception as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
