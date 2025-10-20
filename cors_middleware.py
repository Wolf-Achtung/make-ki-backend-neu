# cors_config.py - Fügen Sie dies zu Ihrer FastAPI-App hinzu

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS-Konfiguration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://make.ki-sicherheit.jetzt",
        "http://localhost:3000",
        "http://localhost:8888",
        "https://*.netlify.app"  # Für Preview-Deployments
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)