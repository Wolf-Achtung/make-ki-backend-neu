# full_init.py
import subprocess

print("🚀 Starte vollständige DB-Initialisierung...")

subprocess.run(["python", "init_pgcrypto.py"])
subprocess.run(["python", "add_unique_email.py"])
subprocess.run(["python", "init_users.py"])

print("✅ DB-Initialisierung fertig!")
