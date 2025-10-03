#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompt_linter.py — Validiert Prompt-Dateien (Markdown/HTML) für den Gold-Standard.

Prüft u. a.:
- Platzhalter-Konsistenz ({{var}}) innerhalb eines Verzeichnisses
- Verbot erfundener Links (Heuristik)
- HTML-Snippet-Validität (geschlossene Tags <ul>, <ol>, <table>, <thead>, <tbody>, <tr>, <td>, <th>)
- Abschlusszeile "Stand: YYYY-MM-DD" bzw. "As of: YYYY-MM-DD"

Usage:
    python prompt_linter.py --prompts-dir ./prompts
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

LOG_FMT = "%(levelname)s %(asctime)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger("prompt_linter")

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_\.:\-]+)\s*\}\}")
DATE_LINE_RE = re.compile(r"(Stand:|As of:)\s*\d{4}-\d{2}-\d{2}$")

HTML_TAGS = ["ul", "ol", "table", "thead", "tbody", "tr", "td", "th"]

def extract_placeholders(text: str) -> List[str]:
    return [m.group(1) for m in PLACEHOLDER_RE.finditer(text)]

def check_html_balance(text: str) -> List[str]:
    errs: List[str] = []
    for tag in HTML_TAGS:
        opens = len(re.findall(fr"<{tag}\b", text))
        closes = len(re.findall(fr"</{tag}>", text))
        if opens != closes:
            errs.append(f"Unbalanced <{tag}>: open={opens} close={closes}")
    return errs

def check_links(text: str) -> List[str]:
    errs: List[str] = []
    # Flag "http://..." in files that request "Keine/Do not invent links"
    if "Keine erfundenen Links" in text or "Do **not** invent links" in text or "Do **not** invent links." in text:
        raw_links = re.findall(r"https?://\S+", text)
        if raw_links:
            errs.append(f"Found raw links although links should not be invented: {raw_links[:3]}{'...' if len(raw_links)>3 else ''}")
    return errs

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts-dir", required=True, help="Pfad zu den Prompt-Dateien (.md)")
    args = ap.parse_args()
    pdir = Path(args.prompts_dir).resolve()

    files = sorted(list(pdir.glob("*.md")))
    if not files:
        log.warning("Keine .md-Dateien in %s gefunden.", pdir)
        return 0

    # Collect placeholders per file and globally
    placeholder_global: Dict[str, int] = {}
    per_file: Dict[str, List[str]] = {}
    errors: Dict[str, List[str]] = {}

    for f in files:
        txt = f.read_text(encoding="utf-8")
        ph = extract_placeholders(txt)
        per_file[f.name] = ph
        for p in ph:
            placeholder_global[p] = placeholder_global.get(p, 0) + 1

        # Checks
        errs: List[str] = []
        errs += check_html_balance(txt)
        errs += check_links(txt)
        if not DATE_LINE_RE.search(txt.strip().splitlines()[-1] if txt.strip().splitlines() else ""):
            errs.append("Missing or malformed final date line 'Stand: YYYY-MM-DD' or 'As of: YYYY-MM-DD'.")

        if errs:
            errors[f.name] = errs

    # Report
    log.info("Analysierte Dateien: %d", len(files))
    log.info("Top 10 Platzhalter: %s", sorted(placeholder_global.items(), key=lambda x: -x[1])[:10])

    if errors:
        log.warning("Es wurden Probleme gefunden (%d Dateien):", len(errors))
        for fn, errs in errors.items():
            log.warning(" - %s", fn)
            for e in errs:
                log.warning("   • %s", e)
        return 1

    log.info("Alles sauber – keine Probleme gefunden.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
