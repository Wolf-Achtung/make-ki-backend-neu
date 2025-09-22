#!/usr/bin/env python3
"""
CI Preflight for Gold-Standard Report
Checks:
1) Python syntax of project files
2) Templates renderability (basic Jinja render with stub data)
3) Prompt hygiene (no story triggers, no raw Jinja tokens)
4) Data sanity (whitelist JSON structure)
Exit code 1 on critical issues.
"""
import os, sys, json, re, pathlib, traceback

ROOT = pathlib.Path(os.getcwd())
errors = [] ; warns = []

# 1) Python syntax
def check_syntax():
    import py_compile
    for p in ROOT.rglob("*.py"):
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:
            errors.append(f"SyntaxError in {p}: {e}")

# 2) Templates
def check_templates():
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    tpl_dir = os.getenv("TEMPLATE_DIR", "templates")
    env = Environment(loader=FileSystemLoader(tpl_dir), autoescape=select_autoescape())
    for name in ["pdf_template.html", "pdf_template_en.html"]:
        try:
            tpl = env.get_template(name)
            dummy = {
                "meta":{"company_name":"Test GmbH","branche":"test","groesse":"kmU","standort":"Berlin","date":"01.01.2025","as_of":"2025-01-01"},
                "executive_summary":"…","quick_wins":"…","risks":"…","recommendations":"…","roadmap":"…",
                "tools_table":"<table></table>","funding_table":"<table></table>",
                "funding_realtime":"","funding_deadlines":"","tools_news":"","regwatch":"","gamechanger":"","appendix":""
            }
            html = tpl.render(**dummy)
            if "{{" in html or "{%" in html:
                errors.append(f"Template {name} ließ Tokens im Output zurück.")
        except Exception as e:
            errors.append(f"Template {name} renderte nicht: {e}")

# 3) Prompt hygiene
STORY = re.compile(r"\b(Ein Unternehmen|Imagine|Consider|For instance)\b", re.I)
def check_prompts():
    base = ROOT / "prompts"
    if not base.exists(): 
        warns.append("Ordner prompts/ fehlt – überspringe Prompt-Checks.")
        return
    for p in base.rglob("*.md"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if STORY.search(txt): warns.append(f"Story-Trigger in {p}")
        if re.search(r"{{[^}{]+}}|{%-?|-%}|{%", txt): warns.append(f"Jinja-Tokens in {p} – bitte entfernen")
        if "prompts" in str(p) and not ("/de/" in str(p).replace('\\','/') or "/en/" in str(p).replace('\\','/')):
            warns.append(f"{p} liegt nicht unter prompts/de oder prompts/en")

# 4) Data sanity
def check_data():
    req_tool = {"name", "category", "hosting", "note"}
    req_funding = {"name","region","target","benefit","status","source","as_of"}
    bad = 0
    for f in ["tool_whitelist.json","funding_whitelist.json","funding_states.json"]:
        p = ROOT / "data" / f
        if not p.exists(): continue
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(arr, list):
                errors.append(f"{f}: erwartet Liste")
                continue
            for i, r in enumerate(arr[:5]):
                keys = set(r.keys())
                need = req_tool if "tool" in f else req_funding
                if not need.issubset(keys):
                    warns.append(f"{f} Eintrag {i}: fehlende Felder {list(need-keys)}")
        except Exception as e:
            errors.append(f"{f}: JSON-Fehler {e}")
    if bad: errors.append("Daten-Whitelist inkonsistent.")

if __name__ == "__main__":
    try:
        check_syntax()
        check_templates()
        check_prompts()
        check_data()
    except Exception as e:
        errors.append(f"Preflight crash: {e}\n{traceback.format_exc()}")
    for w in warns: print("WARN:", w)
    for e in errors: print("ERROR:", e)
    sys.exit(1 if errors else 0)
