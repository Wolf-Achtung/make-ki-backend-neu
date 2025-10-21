#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix Login Passwörter - Setzt temporäre Klartext-Passwörter für Tests
WICHTIG: Nur für Entwicklung/Tests verwenden!
"""

import os
import sys
import psycopg2

def main():
    # Hole DATABASE_URL aus Umgebungsvariablen
    DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL nicht gefunden in Umgebungsvariablen", file=sys.stderr)
        print("   Stelle sicher, dass die Variable in Railway gesetzt ist", file=sys.stderr)
        sys.exit(1)
    
    print("🔧 Fixe Login-Passwörter...")
    print(f"📍 Verwende Datenbank: {DATABASE_URL[:30]}...")
    
    try:
        # Verbinde mit der Datenbank
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Setze temporäre Test-Passwörter (Klartext für Kompatibilität)
        test_users = [
            ("wolf.hohl@web.de", "test123", "user"),
            ("bewertung@ki-sicherheit.jetzt", "admin123", "admin")
        ]
        
        for email, password, role in test_users:
            # Update Passwort als Klartext (wird von verify_password akzeptiert)
            cur.execute("""
                UPDATE users 
                SET password_hash = %s
                WHERE email = %s
                RETURNING id, email, role
            """, (password, email))
            
            result = cur.fetchone()
            if result:
                print(f"✅ {email}: Passwort auf '{password}' gesetzt")
            else:
                print(f"⚠️  {email}: User nicht gefunden - wird angelegt")
                # Falls User nicht existiert, lege ihn an
                cur.execute("""
                    INSERT INTO users (email, password_hash, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) DO UPDATE 
                    SET password_hash = EXCLUDED.password_hash
                """, (email, password, role))
                print(f"✅ {email}: User angelegt mit Passwort '{password}'")
        
        # Committe die Änderungen
        conn.commit()
        print("\n✅ Alle Passwörter erfolgreich gesetzt!")
        
        # Zeige Test-Logins
        print("\n" + "="*50)
        print("📝 TESTE DEN LOGIN MIT:")
        print("="*50)
        print("\n🧑 Normal-User:")
        print("   Email: wolf.hohl@web.de")
        print("   Passwort: test123")
        print("\n👨‍💼 Admin-User:")
        print("   Email: bewertung@ki-sicherheit.jetzt")
        print("   Passwort: admin123")
        print("\n⚠️  WICHTIG: Dies sind temporäre Test-Passwörter!")
        print("   Nach erfolgreichem Login solltest du sie ändern!")
        print("="*50)
        
        # Prüfe ob weitere User existieren
        cur.execute("SELECT COUNT(*) as total FROM users")
        total = cur.fetchone()
        print(f"\nℹ️  Insgesamt {total[0]} User in der Datenbank")
        
        cur.close()
        conn.close()
        print("\n✅ Script erfolgreich beendet")
        return 0
        
    except psycopg2.OperationalError as e:
        print(f"❌ Datenbankverbindung fehlgeschlagen: {e}", file=sys.stderr)
        print("   Prüfe ob DATABASE_URL korrekt ist", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())