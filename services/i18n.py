# services/i18n.py
def normalize_lang(lang: str | None) -> str:
    """
    Normalisiert Sprachangaben auf 'de' oder 'en'.
    Akzeptiert 'de', 'de-DE', 'DE', 'en', 'en-US', etc.
    """
    if not lang:
        return "de"
    l = str(lang).strip().lower()
    return "de" if l.startswith("de") else "en"
