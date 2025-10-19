# -*- coding: utf-8 -*-
"""Security helpers: password verification and token issuing."""
from __future__ import annotations

import hmac
import os
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")

pwd_context = CryptContext(schemes=["bcrypt", "argon2"], deprecated="auto")
_signer = TimestampSigner(SECRET_KEY)


def verify_password(plain_password: str, stored_hash_or_plain: str) -> bool:
    """
    Try to verify using standard password hashes (bcrypt/argon2). If that fails,
    fall back to a constant-time comparison for legacy plaintext storage.
    """
    if not stored_hash_or_plain:
        return False
    try:
        if pwd_context.identify(stored_hash_or_plain):
            return pwd_context.verify(plain_password, stored_hash_or_plain)
    except Exception:
        # If passlib can't handle the pattern, fall through to constant-time.
        pass
    # Legacy/plain comparison (not recommended; kept for compatibility only)
    return hmac.compare_digest(plain_password, stored_hash_or_plain)


def create_access_token(subject: str, max_age_seconds: int = 24 * 60 * 60) -> str:
    # TimestampSigner does not embed expiry, but we use max_age on verification.
    return _signer.sign(subject.encode("utf-8")).decode("utf-8")


def verify_access_token(token: str, max_age_seconds: int = 24 * 60 * 60) -> Optional[str]:
    try:
        return _signer.unsign(token, max_age=max_age_seconds).decode("utf-8")
    except (BadSignature, SignatureExpired):
        return None
