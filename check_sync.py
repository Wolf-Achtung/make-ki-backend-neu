import json
import re
import requests

# Felder laden
with open("fields.json", "r") as f:
    fields = json.load(f)

# Index.html per URL laden
URL = "https://make.ki-sicherheit.jetzt/formular/index.html"
response = requests.get(URL)
html = response.text

# Prüfen ob alle Felder vorhanden sind
missing = []
for key in fields.keys():
    if not re.search(f'name=["\']{key}["\']', html):
        missing.append(key)

if missing:
    print("🚨 Folgende Felder fehlen oder sind inkonsistent in index.html:", missing)
else:
    print("✅ Alle Feldnamen sind synchron!")
