#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FINALE PASSWORT-FIX - Setzt alle Passwörter mit korrekten bcrypt-Hashes

Dieses Script:
1. Liest alle User aus create_tables_and_init.py
2. Erstellt bcrypt-Hashes mit Python passlib (kompatibel mit PostgreSQL)
3. Updated alle Passwörter in der Datenbank
4. Verifiziert dass der Login funktioniert

EINMALIG AUSFÜHREN nach Deploy!
"""

import os
import sys
import psycopg2
from passlib.context import CryptContext

# Passlib Context - gleiche Config wie in security.py
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__ident="2b"
)

# User-Daten aus create_tables_and_init.py
INITIAL_USERS = [
    ("j.hohl@freenet.de", "passjhohl11!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin11!", "user"),
    ("post@zero2.de", "passzero11!", "user"),
    ("giselapeter@peter-partner.de", "passgisela11!", "user"),
    ("stephan@meyer-brehm.de", "passstephan11!", "user"),
    ("wolf.hohl@web.de", "test123", "user"),  # Test-User
    ("geffertj@mac.com", "passjens11!", "user"),
    ("geffertkilian@gmail.com", "passkili11!", "user"),
    ("levent.graef@posteo.de", "passlevgr11!", "user"),
    ("birgit.cook@ulitzka-partner.de", "passbirg111!", "user"),
    ("alexander.luckow@icloud.com", "passbirg11!", "user"),
    ("frank.beer@kabelmail.de", "passfrab11!", "user"),
    ("patrick@silk-relations.com", "passpat11!", "user"),
    ("marc@trailerhaus-onair.de", "passmarct11!", "user"),
    ("norbert@trailerhaus.de", "passgis2r11!", "user"),
    ("sonia-souto@mac.com", "pass-son11!", "user"),
    ("christian.ulitzka@ulitzka-partner.de", "pass2rigz11!", "user"),
    ("srack@gmx.net", "pass2rack11!", "user"),
    ("buss@maria-hilft.de", "pass2mar11!", "user"),
    ("bewertung@ki-sicherheit.jetzt", "test123", "admin")  # Admin mit test123
]

def log(msg: str):
    """Logging mit Flush für Railway"""
    print(msg, flush=True)

def main():
    DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")
    
    if not DATABASE_URL:
        log("❌ DATABASE_URL nicht gefunden in Umgebungsvariablen")
        return 1
    
    log("="*60)
    log("🔧 FINALE PASSWORT-FIX - Setze bcrypt-Hashes")
    log("="*60)
    log(f"📊 {len(INITIAL_USERS)} User werden aktualisiert")
    log(f"🔗 Datenbank: {DATABASE_URL[:40]}...")
    log("")
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()
        
        success_count = 0
        error_count = 0
        
        for email, password, role in INITIAL_USERS:
            try:
                # Erstelle bcrypt-Hash mit Python passlib
                password_hash = pwd_context.hash(password)
                
                # Update User
                cur.execute("""
                    INSERT INTO users (email, password_hash, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) 
                    DO UPDATE SET 
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (email, password_hash, role))
                
                result = cur.fetchone()
                if result:
                    log(f"  ✅ {email} ({role})")
                    success_count += 1
                    
            except Exception as e:
                log(f"  ❌ {email}: {e}")
                error_count += 1
        
        # Commit wenn alles erfolgreich
        if error_count == 0:
            conn.commit()
            log("")
            log(f"✅ Alle {success_count} Passwörter erfolgreich aktualisiert!")
        else:
            log(f"\n⚠️ {error_count} Fehler aufgetreten - Rollback")
            conn.rollback()
            return 1
        
        # Verifiziere die Test-User
        log("")
        log("="*60)
        log("🧪 VERIFIZIERE TEST-USER")
        log("="*60)
        
        test_users = [
            ("wolf.hohl@web.de", "test123"),
            ("bewertung@ki-sicherheit.jetzt", "test123")
        ]
        
        for email, password in test_users:
            cur.execute("SELECT password_hash FROM users WHERE email = %s", (email,))
            result = cur.fetchone()
            
            if result:
                stored_hash = result[0]
                # Verifiziere mit passlib
                is_valid = pwd_context.verify(password, stored_hash)
                
                if is_valid:
                    log(f"  ✅ {email}: Passwort korrekt verifiziert")
                else:
                    log(f"  ❌ {email}: Passwort-Verifizierung fehlgeschlagen!")
                    error_count += 1
            else:
                log(f"  ❌ {email}: User nicht gefunden!")
                error_count += 1
        
        cur.close()
        conn.close()
        
        if error_count == 0:
            log("")
            log("="*60)
            log("🎉 SETUP ERFOLGREICH ABGESCHLOSSEN!")
            log("="*60)
            log("")
            log("📱 TESTE DEN LOGIN:")
            log("")
            log("👤 Normal-User:")
            log("   Email: wolf.hohl@web.de")
            log("   Passwort: test123")
            log("")
            log("👨‍💼 Admin-User:")
            log("   Email: bewertung@ki-sicherheit.jetzt")
            log("   Passwort: test123")
            log("")
            log("⚠️  WICHTIG:")
            log("   1. Nach erstem Login Passwörter ändern!")
            log("   2. ENABLE_ADMIN_UPLOAD=false setzen!")
            log("   3. Diese Datei aus dem Repository entfernen!")
            log("="*60)
            return 0
        else:
            log("\n❌ Setup mit Fehlern abgeschlossen")
            return 1
            
    except Exception as e:
        log(f"❌ Kritischer Fehler: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
