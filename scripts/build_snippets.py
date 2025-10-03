#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_snippets.py — Gold-Standard data builder for Prompt-Creator-Assistent

- Normalisiert Daten aus dem Ordner 'data/' (CSV/JSON/MD)
- Erzeugt robuste HTML-Snippets: TOOLS_HTML, FUNDING_HTML, COMPLIANCE_HTML
- Prüft Schemata & meldet Warnungen statt zu brechen
- Schreibt einen Build-Report (JSON)

Usage:
    python build_snippets.py --data-dir ./data --out-dir ./output --date 2025-10-03
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

# ------------- Logging setup -------------
LOG_FMT = "%(levelname)s %(asctime)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger("build_snippets")

# ------------- Utilities -------------
def read_text_if_exists(p: Path) -> Optional[str]:
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("Failed reading %s: %s", p, e)
    return None

def read_json_if_exists(p: Path) -> Optional[Any]:
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Failed parsing JSON %s: %s", p, e)
    return None

def sniff_delimiter(header_line: str) -> str:
    if header_line.count(";") > header_line.count(","):
        return ";"
    return ","

def read_csv_flexible(p: Path) -> List[Dict[str, str]]:
    """Robust CSV reader that tolerates ';' or ',' delimiters and BOM."""
    try:
        raw = p.read_text(encoding="utf-8-sig")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if not lines:
            return []
        delim = sniff_delimiter(lines[0])
        reader = csv.DictReader(lines, delimiter=delim)
        rows = [ { (k or '').strip(): (v or '').strip() for k, v in row.items() } for row in reader ]
        return rows
    except Exception as e:
        log.warning("Failed parsing CSV %s: %s", p, e)
        return []

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def today_iso(date_override: Optional[str]) -> str:
    if date_override:
        return date_override
    return dt.date.today().isoformat()

# ------------- Core builders -------------
def load_schema(data_dir: Path) -> Dict[str, Any]:
    """Loads schema.mapping.json (either in data/ or build/), else defaults."""
    candidates = [
        data_dir / "schema.mapping.json",
        data_dir.parent / "build" / "schema.mapping.json",
    ]
    for c in candidates:
        s = read_json_if_exists(c)
        if s:
            log.info("Loaded schema mapping from %s", c)
            return s
    log.warning("No schema.mapping.json found; using built-in defaults.")
    return {
        "tools.csv": {"industry_slugs_col": "industry_slugs", "size_col": "company_size", "region_col": None},
        "foerdermittel.csv": {"industry_slugs_col": "industry_slugs", "size_col": "target_group", "region_col": "region"},
        "size_buckets": ["solo", "team_2_10", "kmu_11_100"],
        "form_size_to_bucket": {"solo": "solo", "team": "team_2_10", "kmu": "kmu_11_100"}
    }

def norm_size(val: str, schema: Dict[str, Any]) -> str:
    v = (val or "").strip().lower()
    if v in {"any", ""}:
        return "any"
    # Direct match of buckets
    if v in set(schema.get("size_buckets", [])):
        return v
    # Form mapping
    m = schema.get("form_size_to_bucket", {})
    return m.get(v, v)

def build_tools_html(data_dir: Path, out_dir: Path, schema: Dict[str, Any], date_str: str, report: Dict[str, Any]) -> None:
    # Prefer data/tools.csv; fallback to tools.md (parse simple bullet lists) else empty.
    tools_csv = data_dir / "tools.csv"
    rows = []
    if tools_csv.exists():
        rows = read_csv_flexible(tools_csv)
        report["tools_csv_rows"] = len(rows)
    else:
        # Try to parse tools.md as bullets of form "- [Name](url): desc"
        md = read_text_if_exists(data_dir / "tools.md") or ""
        for line in md.splitlines():
            line = line.strip()
            if line.startswith("- [") and "](" in line:
                name = line.split("[",1)[1].split("]",1)[0]
                url = line.split("](",1)[1].split(")",1)[0]
                desc = line.split("):",1)[1].strip() if "):" in line else ""
                rows.append({"tool_name": name, "url": url, "short_description": desc, "industry": "", "industry_slugs": "", "company_size": "any"})
        report["tools_md_rows"] = len(rows)

    if not rows:
        log.warning("No tools rows found. Creating empty TOOLS_HTML.")
        (out_dir / "TOOLS_HTML.html").write_text(f"<p>Keine Tools gefunden. Stand: {html.escape(date_str)}</p>", encoding="utf-8")
        return

    # Normalize columns
    ind_col = schema["tools.csv"]["industry_slugs_col"]
    size_col = schema["tools.csv"]["size_col"]

    items = []
    for r in rows:
        tool = {
            "name": r.get("tool_name") or r.get("Tool-Name") or r.get("name") or "",
            "url": r.get("url") or "",
            "desc": r.get("short_description") or r.get("Kurze Beschreibung") or r.get("desc") or "",
            "industry_slugs": [s.strip().lower() for s in (r.get(ind_col) or r.get("Branche-Slugs") or "").split(";") if s.strip()],
            "company_size": norm_size(r.get(size_col) or r.get("Unternehmensgröße") or "any", schema),
            "pricing": r.get("pricing") or r.get("Preis") or "",
            "tags": r.get("tags") or r.get("Tags") or "",
            "dpa": r.get("dpa_available") or r.get("AVV/DPA") or "",
            "compat": r.get("compatibility_integrations") or r.get("Kompatibilität/Integration") or "",
            "data_residency": r.get("data_residency") or r.get("Datensitz") or "",
        }
        items.append(tool)

    # Render HTML
    parts = [f'<ol class="tools-list">']
    for t in items:
        safe_name = html.escape(t["name"])
        safe_url = html.escape(t["url"])
        safe_desc = html.escape(t["desc"])
        meta_bits = []
        if t["pricing"]:
            meta_bits.append(f"Preis: {html.escape(t['pricing'])}")
        if t["company_size"] and t["company_size"] != "any":
            meta_bits.append(f"Größe: {html.escape(t['company_size'])}")
        if t["data_residency"]:
            meta_bits.append(f"Datensitz: {html.escape(t['data_residency'])}")
        if t["dpa"]:
            meta_bits.append(f"AVV/DPA: {html.escape(t['dpa'])}")
        if t["compat"]:
            meta_bits.append(f"Integrationen: {html.escape(t['compat'])}")
        meta = " — ".join(meta_bits)
        parts.append(f'<li><b><a href="{safe_url}" rel="noopener" target="_blank">{safe_name}</a></b>: {safe_desc}'
                     f'{(" — <i>"+meta+"</i>") if meta else ""}</li>')
    parts.append("</ol>")
    parts.append(f'<p><small>Stand: {html.escape(date_str)}</small></p>')
    html_out = "\n".join(parts)
    (out_dir / "TOOLS_HTML.html").write_text(html_out, encoding="utf-8")
    report["TOOLS_HTML"] = {"items": len(items)}

def build_funding_html(data_dir: Path, out_dir: Path, schema: Dict[str, Any], date_str: str, report: Dict[str, Any]) -> None:
    # Prefer foerdermittel.csv; fallback to foerdermittel.md (table) else empty.
    rows = []
    csv_path = data_dir / "foerdermittel.csv"
    if csv_path.exists():
        rows = read_csv_flexible(csv_path)
        report["funding_csv_rows"] = len(rows)
    else:
        md = read_text_if_exists(data_dir / "foerdermittel.md") or ""
        # very simple pipe-table parser
        lines = [l.strip() for l in md.splitlines() if l.strip().startswith("|")]
        if len(lines) >= 2:
            headers = [h.strip() for h in lines[0].strip("|").split("|")]
            for ln in lines[2:]:
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if len(cells) != len(headers): 
                    continue
                rows.append(dict(zip(headers, cells)))
        report["funding_md_rows"] = len(rows)

    if not rows:
        (out_dir / "FUNDING_HTML.html").write_text(f"<p>Keine Förderprogramme erfasst. Stand: {html.escape(date_str)}</p>", encoding="utf-8")
        log.warning("No funding rows found.")
        return

    # Normalize columns
    normalize = lambda r, *cols: next((r.get(c, "") for c in cols if c in r and r.get(c)), "")
    items = []
    for r in rows:
        items.append({
            "name": normalize(r, "name", "Name"),
            "region": normalize(r, "region", "Region"),
            "type": normalize(r, "type", "Typ"),
            "rate": normalize(r, "rate_percent", "Fördersatz (%)", "Satz/Max"),
            "max": normalize(r, "max_amount_eur", "Max (€)", "Max_Betrag"),
            "deadline": normalize(r, "deadline", "Deadline"),
            "link": normalize(r, "link", "Link"),
        })

    # Render HTML table with thead/tbody
    thead = "<thead><tr><th>Programm</th><th>Region</th><th>Typ</th><th>Satz/Max</th><th>Deadline</th><th>Link</th></tr></thead>"
    rows_html = []
    for it in items:
        link_html = f'<a href="{html.escape(it["link"])}" target="_blank" rel="noopener">Link</a>' if it["link"] else ""
        rows_html.append(
            f'<tr><td>{html.escape(it["name"])}</td><td>{html.escape(it["region"])}</td>'
            f'<td>{html.escape(it["type"])}</td><td>{html.escape(it["rate"])} / {html.escape(it["max"])}</td>'
            f'<td>{html.escape(it["deadline"])}</td><td>{link_html}</td></tr>'
        )
    table = f'<table>{thead}<tbody>' + "\n".join(rows_html) + "</tbody></table>\n" + f'<p><small>Stand: {html.escape(date_str)}</small></p>'
    (out_dir / "FUNDING_HTML.html").write_text(table, encoding="utf-8")
    report["FUNDING_HTML"] = {"items": len(items)}

def build_compliance_html(data_dir: Path, out_dir: Path, date_str: str, report: Dict[str, Any]) -> None:
    # Merge checklists if present
    parts: List[str] = []
    added = 0
    for fn in ["check_datenschutz.md", "check_innovationspotenzial.md"]:
        p = data_dir / fn
        txt = read_text_if_exists(p)
        if txt:
            # convert basic markdown bullets to <ul> / <li>
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            lis = []
            for ln in lines:
                if ln.startswith("- "):
                    lis.append("<li>" + html.escape(ln[2:].strip()) + "</li>")
            if lis:
                parts.append("<ul>" + "\n".join(lis) + "</ul>")
                added += len(lis)
    if not parts:
        (out_dir / "COMPLIANCE_HTML.html").write_text(f"<p>Keine Compliance-Checklisten vorhanden. Stand: {html.escape(date_str)}</p>", encoding="utf-8")
        return
    parts.append(f'<p><small>Stand: {html.escape(date_str)}</small></p>')
    (out_dir / "COMPLIANCE_HTML.html").write_text("\n".join(parts), encoding="utf-8")
    report["COMPLIANCE_HTML"] = {"items": added}

def build_benchmarks(data_dir: Path, out_dir: Path, date_str: str, report: Dict[str, Any]) -> None:
    # Gather benchmark_*.csv and benchmarks_*.json, normalise into a single JSON for downstream use
    csv_files = list(data_dir.glob("benchmark_*.csv"))
    json_files = list(data_dir.glob("benchmarks_*.json"))
    aggregated = {"from_csv": {}, "from_json": {}}

    # CSVs keyed by industry (from filename)
    for p in csv_files:
        industry = p.stem.replace("benchmark_", "").lower()
        rows = read_csv_flexible(p)
        aggregated["from_csv"][industry] = rows

    # JSON files: just load and store by stem
    for p in json_files:
        try:
            aggregated["from_json"][p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Invalid JSON %s: %s", p, e)

    out_json = {
        "generated_at": date_str,
        "csv": aggregated["from_csv"],
        "json": aggregated["from_json"]
    }
    (out_dir / "benchmarks.json").write_text(json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8")
    report["benchmarks"] = {"csv_files": len(csv_files), "json_files": len(json_files)}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data", help="Path to data directory")
    ap.add_argument("--out-dir", default="output", help="Path to output directory")
    ap.add_argument("--date", default=None, help="ISO date override for 'Stand:'")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    ensure_dir(out_dir)
    date_str = today_iso(args.date)
    report: Dict[str, Any] = {"date": date_str, "data_dir": str(data_dir), "out_dir": str(out_dir)}

    schema = load_schema(data_dir)
    build_tools_html(data_dir, out_dir, schema, date_str, report)
    build_funding_html(data_dir, out_dir, schema, date_str, report)
    build_compliance_html(data_dir, out_dir, date_str, report)
    build_benchmarks(data_dir, out_dir, date_str, report)

    # include form mapping if present
    fm = read_json_if_exists(data_dir.parent / "build" / "form_mapping.json") or {}
    report["form_mapping_keys"] = len(fm)

    (out_dir / "BUILD_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Done. Report written to %s", out_dir / "BUILD_REPORT.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
