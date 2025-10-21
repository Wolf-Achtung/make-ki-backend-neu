#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Komplettes Datenbank-Setup für KI-Status-Report
- Erstellt alle notwendigen Tabellen
- Installiert pgcrypto Extension
- Legt alle User an
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Datenbank-URL aus Umgebung
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL nicht gefunden in Umgebungsvariablen", file=sys.stderr)
    sys.exit(1)

# User-Daten für die Initialisierung
INITIAL_USERS = [
    ("j.hohl@freenet.de", "passjhohl11!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin11!", "user"),
    ("post@zero2.de", "passzero11!", "user"),
    ("giselapeter@peter-partner.de", "passgisela11!", "user"),
    ("stephan@meyer-brehm.de", "passstephan11!", "user"),
    ("wolf.hohl@web.de", "passwolf11!", "user"),
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
    ("bewertung@ki-sicherheit.jetzt", "passadmin11!", "admin")
]

def log(msg: str):
    """Logging mit Flush für Railway"""
    print(msg, flush=True)

def create_tables(cur):
    """Erstellt alle notwendigen Tabellen"""
    
    # Users Tabelle
    log("📊 Erstelle users Tabelle...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'user' NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Index für Email (Performance)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email_lower 
        ON users (LOWER(email));
    """)
    
    # Feedback Tabelle (falls benötigt)
    log("📊 Erstelle feedback Tabelle...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255) NOT NULL,
            session_id VARCHAR(255),
            feedback_type VARCHAR(50),
            feedback_text TEXT,
            rating INTEGER,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Reports/Tasks Tabelle (falls benötigt für Queue)
    log("📊 Erstelle reports Tabelle...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            task_id VARCHAR(255) UNIQUE NOT NULL,
            user_email VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            report_data JSONB,
            pdf_url TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
    """)
    
    # Index für task_id
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_task_id 
        ON reports (task_id);
    """)
    
    log("✅ Alle Tabellen erstellt/verifiziert")

def setup_extensions(cur):
    """Installiert notwendige PostgreSQL Extensions"""
    log("🔧 Installiere pgcrypto Extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    log("✅ pgcrypto Extension bereit")

def insert_users(cur):
    """Fügt alle initialen User ein"""
    log("👥 Füge User ein...")
    
    success_count = 0
    error_count = 0
    
    for email, password, role in INITIAL_USERS:
        try:
            cur.execute("""
                INSERT INTO users (email, password_hash, role)
                VALUES (%s, crypt(%s, gen_salt('bf')), %s)
                ON CONFLICT (email) 
                DO UPDATE SET 
                    password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, email
            """, (email, password, role))
            
            result = cur.fetchone()
            if result:
                log(f"   ✓ {email} ({role})")
                success_count += 1
                
        except Exception as e:
            log(f"   ❌ Fehler bei {email}: {e}")
            error_count += 1
    
    log(f"✅ User-Import abgeschlossen: {success_count} erfolgreich, {error_count} Fehler")
    return success_count, error_count

def verify_setup(cur):
    """Verifiziert das Setup"""
    log("\n🔍 Verifiziere Setup...")
    
    # Prüfe User-Count
    cur.execute("SELECT COUNT(*) as count FROM users")
    user_count = cur.fetchone()['count']
    log(f"   • User in Datenbank: {user_count}")
    
    # Prüfe Admin-User
    cur.execute("""
        SELECT email, role 
        FROM users 
        WHERE role = 'admin'
    """)
    admins = cur.fetchall()
    for admin in admins:
        log(f"   • Admin-User: {admin['email']}")
    
    # Prüfe Test-User
    cur.execute("""
        SELECT email, role 
        FROM users 
        WHERE email = 'wolf.hohl@web.de'
    """)
    test_user = cur.fetchone()
    if test_user:
        log(f"   • Test-User bereit: {test_user['email']}")
    
    return user_count > 0

def main():
    """Hauptfunktion"""
    log("🚀 Starte Datenbank-Setup für KI-Status-Report...")
    log(f"📍 Verwende DATABASE_URL: {DATABASE_URL[:30]}...")
    
    try:
        # Verbindung aufbauen
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        conn.autocommit = False  # Explizite Transaktionen
        cur = conn.cursor()
        
        # Aktuelle Datenbank anzeigen
        cur.execute("SELECT current_database() as db")
        db_info = cur.fetchone()
        log(f"📌 Verbunden mit Datenbank: {db_info['db']}")
        
        # Setup durchführen
        setup_extensions(cur)
        create_tables(cur)
        success, errors = insert_users(cur)
        
        # Commit wenn erfolgreich
        if errors == 0:
            conn.commit()
            log("✅ Transaktion erfolgreich committed")
        else:
            log(f"⚠️ {errors} Fehler aufgetreten, committe trotzdem...")
            conn.commit()
        
        # Verifizieren
        if verify_setup(cur):
            log("\n" + "="*50)
            log("✅ SETUP ERFOLGREICH ABGESCHLOSSEN!")
            log("="*50)
            log("\n📝 Teste den Login mit:")
            log("   Email: wolf.hohl@web.de")
            log("   Passwort: passwolf11!")
            log("\n👨‍💼 Admin-Login:")
            log("   Email: bewertung@ki-sicherheit.jetzt")
            log("   Passwort: passadmin11!")
            log("\n⚠️ WICHTIG: Ändere die Passwörter nach dem ersten Login!")
            log("⚠️ WICHTIG: Setze ENABLE_ADMIN_UPLOAD=false nach dem Setup!")
            return 0
        else:
            log("⚠️ Setup abgeschlossen, aber Verifizierung zeigt Probleme")
            return 1
            
    except Exception as e:
        log(f"❌ Kritischer Fehler: {e}")
        if 'conn' in locals():
            try:
                conn.rollback()
                log("❌ Transaktion zurückgerollt")
            except:
                pass
        return 1
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
        log("🔚 Datenbankverbindung geschlossen")

if __name__ == "__main__":
    sys.exit(main())