# -*- coding: utf-8 -*-
"""Security helpers: password verification and token issuing.

FINALE VERSION - Unterstützt beide Hash-Formate:
- PostgreSQL crypt() mit bcrypt
- Python passlib bcrypt
"""
from __future__ import annotations

import os
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")

# Konfiguriere passlib für beide bcrypt-Formate
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__ident="2b"  # Standard bcrypt identifier
)

_signer = TimestampSigner(SECRET_KEY)


def verify_password(plain_password: str, stored_hash_or_plain: str) -> bool:
    """
    Verifiziert Passwörter gegen verschiedene Hash-Formate:
    1. Python bcrypt ($2b$...)
    2. PostgreSQL bcrypt ($2a$... oder $2b$...)
    3. Fallback: Klartext-Vergleich (nur für Legacy/Migration)
    """
    if not stored_hash_or_plain:
        return False
    
    # Prüfe ob es ein bcrypt-Hash ist (PostgreSQL oder Python)
    # PostgreSQL: $2a$ oder $2b$
    # Python passlib: $2b$
    if stored_hash_or_plain.startswith(('$2a$', '$2b$', '$2y$')):
        try:
            # Normalisiere PostgreSQL $2a$ zu $2b$ für passlib
            normalized_hash = stored_hash_or_plain
            if normalized_hash.startswith('$2a$'):
                normalized_hash = '$2b$' + normalized_hash[4:]
            
            return pwd_context.verify(plain_password, normalized_hash)
        except Exception as e:
            # Wenn passlib fehlschlägt, logge es aber gib False zurück
            import logging
            logging.getLogger("security").debug(
                f"bcrypt verification failed: {e}"
            )
            return False
    
    # Legacy-Fallback: Direkter String-Vergleich
    # WICHTIG: Dies ist unsicher und sollte nur temporär verwendet werden
    # Nach Migration aller Passwörter zu bcrypt, diesen Teil entfernen
    try:
        import hmac
        return hmac.compare_digest(plain_password, stored_hash_or_plain)
    except Exception:
        return False


def hash_password(plain_password: str) -> str:
    """
    Erstellt einen bcrypt-Hash eines Passworts.
    Dieser Hash ist kompatibel mit PostgreSQL's crypt() Funktion.
    """
    return pwd_context.hash(plain_password)


def create_access_token(subject: str, max_age_seconds: int = 24 * 60 * 60) -> str:
    """Erstellt einen signierten Token für Authentifizierung."""
    return _signer.sign(subject.encode("utf-8")).decode("utf-8")


def verify_access_token(token: str, max_age_seconds: int = 24 * 60 * 60) -> Optional[str]:
    """Verifiziert einen signierten Token."""
    try:
        return _signer.unsign(token, max_age=max_age_seconds).decode("utf-8")
    except (BadSignature, SignatureExpired):
        return None
