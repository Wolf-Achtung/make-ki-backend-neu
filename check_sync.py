# filename: check_sync.py
# -*- coding: utf-8 -*-
# Feld-Synchronisations-Checker (Gold-Standard+)
# Vergleicht das Backend-Schema (shared/report_schema.json) mit den Formular-Quellen (Formbuilder-JS oder HTML).
# Nutzung:
#   python check_sync.py --schema shared/report_schema.json --de path_or_url_to_formbuilder_de.js --en path_or_url_to_formbuilder_en.js
# Ausgabe: JSON mit "missing_in_form", "extra_in_form" pro Sprache.

from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Dict, List, Set
try:
    import requests  # optional für URL-Quellen
except Exception:
    requests = None  # type: ignore

def _load_text(src: str) -> str:
    if re.match(r"^https?://", src):
        if not requests:
            raise RuntimeError("requests not installed – cannot fetch URL")
        r = requests.get(src, timeout=20)
        r.raise_for_status()
        return r.text
    p = Path(src)
    return p.read_text(encoding="utf-8")

def _schema_keys(schema_path: str) -> Set[str]:
    obj = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    fields = obj.get("fields") or obj.get("properties") or {}
    keys = set()
    if isinstance(fields, dict):
        keys |= set(fields.keys())
    # optional: nested groups
    for k, v in (fields or {}).items():
        if isinstance(v, dict):
            children = v.get("children") or v.get("fields") or []
            if isinstance(children, list):
                for sub in children:
                    if isinstance(sub, str):
                        keys.add(sub)
    return keys

def _extract_form_keys(src_text: str) -> Set[str]:
    # 1) Formbuilder-JS: name: 'feld' oder "name": "feld"
    js_names = set(re.findall(r"""name["']\s*:\s*["']([a-zA-Z0-9_\-]+)["']""", src_text))
    if js_names:
        return js_names
    # 2) HTML: name="feld"
    html_names = set(re.findall(r"""name=["']([a-zA-Z0-9_\-]+)["']""", src_text))
    return html_names

def compare(schema_path: str, form_src: str) -> Dict[str, List[str]]:
    schema = _schema_keys(schema_path)
    form_txt = _load_text(form_src)
    form = _extract_form_keys(form_txt)
    missing_in_form = sorted(list(schema - form))
    extra_in_form = sorted(list(form - schema))
    return {"missing_in_form": missing_in_form, "extra_in_form": extra_in_form}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True, help="Pfad zur shared/report_schema.json")
    ap.add_argument("--de", required=False, help="Pfad/URL zum deutschen Formular (formbuilder_de_SINGLE_FULL.js oder HTML)")
    ap.add_argument("--en", required=False, help="Pfad/URL zum englischen Formular (formbuilder_en_SINGLE_FULL.js oder HTML)")
    args = ap.parse_args()

    out = {}
    if args.de:
        out["de"] = compare(args.schema, args.de)
    if args.en:
        out["en"] = compare(args.schema, args.en)

    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
