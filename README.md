# 🚀 KI-Briefing (DSGVO & Fördercheck)

Dieses Projekt erstellt ein individuelles Executive-Briefing inkl. Compliance-Score, Badge und Fördertipps auf Basis deiner Unternehmensdaten.  
Optimiert für kleine Unternehmen & Berater, DSGVO-konform, minimal aufgebaut.

---

## 🗂️ Struktur

| Datei               | Zweck                                       |
|----------------------|--------------------------------------------|
| `index.html`         | Dein Formular + JS, ruft `/briefing` auf   |
| `main.py`            | Flask-API mit `/briefing`                  |
| `gpt_analyze.py`     | GPT-Analyse inkl. Score & Badge            |
| `requirements.txt`   | Python-Abhängigkeiten                      |
| `Dockerfile`         | Für Railway oder lokalen Docker-Deploy     |

---

## 🚀 Deployment auf Railway

1. Repository bei GitHub erstellen, Dateien hochladen
2. Railway öffnen → **„New Project“ → „Deploy from GitHub Repo“**
3. Automatisch wird dein `Dockerfile` erkannt.  
4. Done! Deine App läuft dann z. B. unter `https://make-ki-backend-neu-production.up.railway.app/`

---

## 🔥 Lokale Ausführung (Docker)

```bash
docker build -t ki-briefing .
docker run -p 8000:8000 ki-briefing
