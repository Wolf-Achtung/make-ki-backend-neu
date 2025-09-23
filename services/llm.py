from typing import Optional, Dict
from loguru import logger
import os

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

from services.config import settings

def generate_with_llm(prompt: str, sys_prompt: Optional[str] = None, temperature: float = 0.2) -> Optional[str]:
    """
    Minimal OpenAI Chat Completions wrapper via HTTP (no SDK dependency).
    Only used if OPENAI_API_KEY is set. Returns text or None on failure.
    """
    if not settings.OPENAI_API_KEY:
        return None
    if httpx is None:
        logger.warning("httpx not available; cannot contact OpenAI")
        return None

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt or "You are a helpful assistant that writes concise, factual reports."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature
    }
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return None
