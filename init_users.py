

    # Test-User mit individuellen Passwörtern
    ("j.hohl@freenet.de", "passjhohl!", "user"),
    ("kerstin.geffert@gmail.com", "passkerstin!", "user"),
    ("post@zero2.de", "passzero2!", "user"),
    ("giselapeter@peter-partner.de", "passgisela!", "user"),
    ("stephan@meyer-brehm.de", "passstephan!", "user"),
    ("wolf.hohl@web.de", "passwolfi!", "user"),
    ("geffertj@mac.com", "passjens!", "user"),
    ("geffertkilian@gmail.com", "passkili!", "user"),
    ("levent.graef@posteo.de", "passlevgr!", "user"),
    ("birgit.cook@ulitzka-partner.de", "passbirg!", "user"),
    ("alexander.luckow@icloud.com", "passbirg!", "user"),
    ("frank.beer@kabelmail.de", "passfrab!", "user"),
    ("patrick@silk-relations.com", "passpat!", "user"),
    ("marc@trailerhaus-onair.de", "passmarct!", "user"),
    ("norbert@trailerhaus.de", "passgis2r!", "user"),
    ("sonia-souto@mac.com", "pass-son!", "user"),
    ("christian.ulitzka@ulitzka-partner.de", "pass2rigz!", "user"),
    ("srack@gmx.net", "pass2rack!", "user"),
    ("buss@maria-hilft.de", "pass2mar!", "user"),
    ("bewertung@ki-sicherheit.jetzt", "passadmin1!", "admin"),
]


print("Starte Einfügen/Update der User...")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

for email, password, role in users:
    print(f"Verarbeite: {email}")
    cur.execute("""
        INSERT INTO users (email, password_hash, role)
        VALUES (%s, crypt(%s, gen_salt('bf')), %s)
        ON CONFLICT (email) 
        DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role
    """, (email, password, role))

conn.commit()
cur.close()
conn.close()
print("Alle User erfolgreich angelegt / aktualisiert.")
