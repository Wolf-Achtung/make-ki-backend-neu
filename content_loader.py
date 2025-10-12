# filename: content_loader.py
# -*- coding: utf-8 -*-
"""
Utility to load curated content blocks (bilingual) for injection into the PDF report.

- Prefers preformatted HTML from /content/*.html
- Falls back to .docx text extraction (very lightweight XML parse)
- Optional translation via OpenAI (if OPENAI_API_KEY present)
- Sanitises to an HTML fragment (no <html>/<head>/<body> tags)

ENV:
  CONTENT_DIR        default: ./content
  CONTENT_TRANSLATE  '1'|'true' to translate if only other language available
"""
from __future__ import annotations

from typing import Optional, Tuple
from pathlib import Path
import re
import os

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

def _strip_outer_html(html: str) -> str:
    if not html:
        return ""
    s = html
    s = re.sub(r"(?is)<!doctype.*?>", "", s)
    s = re.sub(r"(?is)<\s*html[^>]*>|</\s*html\s*>", "", s)
    s = re.sub(r"(?is)<\s*head[^>]*>.*?</\s*head\s*>", "", s)
    s = re.sub(r"(?is)<\s*body[^>]*>|</\s*body\s*>", "", s)
    return s.strip()

def _docx_to_html(p: Path) -> str:
    """Very lightweight DOCX text extraction -> <p> lines. No external deps."""
    try:
        import zipfile, xml.etree.ElementTree as ET
        with zipfile.ZipFile(p, "r") as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = re.sub(r'xmlns(:\w+)?="[^"]+"', "", xml)  # strip namespaces for easier parsing
        root = ET.fromstring(xml)
        paras = []
        for t in root.iter():
            if t.tag.endswith("p"):
                texts = [x.text for x in t.iter() if x.tag.endswith("t") and x.text]
                if texts:
                    paras.append("<p>" + re.sub(r"\s+", " ", "".join(texts)).strip() + "</p>")
        return "\n".join(paras)
    except Exception:
        return ""

def _maybe_translate(html: str, lang_target: str) -> str:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key or not html:
        return html  # no translation possible -> original
    # lightweight translation via OpenAI
    try:
        import httpx, json
        sys = "Translate the following HTML fragment. Keep tags, translate only visible text."
        user = f"Target language: {'German' if lang_target.startswith('de') else 'English'}\n\n{html}"
        payload = {
            "model": os.getenv("OPENAI_MODEL_TRANSLATE", os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")),
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "temperature": 0.0,
            "max_tokens": 1500,
        }
        with httpx.Client(timeout=float(os.getenv("OPENAI_TIMEOUT","45"))) as c:
            r = c.post("https://api.openai.com/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json=payload)
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            return _strip_outer_html(content)
    except Exception:
        return html  # fallback

def _load_one(base: Path, stem: str, lang: str) -> Tuple[str, str]:
    """
    Returns (html, source_path_str)
    Tries: stem.<lang>.html -> stem.en.html/de.html -> stem.docx (same language) -> other language with optional translation.
    """
    # prefer language-specific html file: e.g., 4-pillars-ai-readiness.en.html or .de.html
    q = [
        base / f"{stem}.{lang}.html",
        base / f"{stem}.html",  # generic html
    ]
    # DOCX fallback
    q += [
        base / f"{stem}.docx",
        base / f"{stem}.{lang}.docx",
    ]
    for p in q:
        if p.exists():
            if p.suffix.lower() == ".html":
                return _strip_outer_html(_read_text(p)), str(p)
            if p.suffix.lower() == ".docx":
                html = _docx_to_html(p)
                return _strip_outer_html(html), str(p)
    # try other language html and translate (optional)
    other = base / f"{stem}.{ 'en' if lang.startswith('de') else 'de'}.html"
    if other.exists() and (os.getenv("CONTENT_TRANSLATE","1").lower() in {"1","true","yes"}):
        html = _strip_outer_html(_read_text(other))
        return _maybe_translate(html, lang), str(other)
    return "", ""

def load_content_sections(lang: str = "de") -> dict:
    """
    Loads a curated set of sections:
      - 4 pillars
      - legal pitfalls
      - transformation formula 10-20-70
    Returns dict with HTML fragments (may be empty strings).
    """
    base = Path(os.getenv("CONTENT_DIR","content")).resolve()
    sections = {
        "pillars": ("4-pillars-ai-readiness", "4-Saeulen-KI-Readiness"),
        "legal": ("legal-pitfalls-ai", "rechtliche-Stolpersteine-KI-im-Unternehmen"),
        "formula": ("transformation-formula-10-20-70", "Formel-fuer-Transformation"),
    }
    out = {}
    for key, (en_stem, de_stem) in sections.items():
        stem = de_stem if lang.startswith("de") else en_stem
        html, src = _load_one(base, stem, lang)
        out[key] = {"html": html, "source": src}
    return out
# end of file
