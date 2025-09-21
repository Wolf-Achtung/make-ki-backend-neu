# main.py
# FastAPI-Backend (relevante Endpunkte): login (Demo), briefing_async (Report bauen).
# Kernpunkte:
# - Lädt gpt_analyze.py, erkennt async/sync und awaited korrekt.
# - Jinja-Render mit sicheren Defaults (meta.date etc.).
# - PDF-Service Warmup/Call mit robusten Fallbacks.
# - Klare Logs.

from __future__ import annotations
import os, json, asyncio, datetime as dt, logging, inspect, traceback
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s [backend] %(message)s")
log = logging.getLogger("backend")

# ---------- App ----------
app = FastAPI(title="KI-Statusbericht Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ---------- Templates ----------
BASE_DIR = Path(__file__).parent
TPL_DIR = BASE_DIR / "templates"
env = Environment(
    loader=FileSystemLoader(str(TPL_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True, lstrip_blocks=True,
)

# ---------- PDF Service ----------
PDF_BASE = os.getenv("PDF_SERVICE_BASE", "https://make-ki-pdfservice-production.up.railway.app")

async def warmup_pdf_service(rid: str):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
            r = await client.get(f"{PDF_BASE}/health")
            log.info("[PDF] rid=%s warmup %s", rid, r.status_code)
    except Exception:
        log.warning("[PDF] rid=%s warmup failed", rid)

async def send_html_to_pdf_service(html: str, rid: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            r = await client.post(f"{PDF_BASE}/generate-pdf", json={"html": html})
            log.info("[PDF] rid=%s attempt status=%s", rid, r.status_code)
            if r.status_code == 200:
                return r.content
    except Exception:
        log.exception("[PDF] rid=%s call failed", rid)
    return None

# ---------- Analyze Loader ----------
def _load_analyze_module():
    try:
        import importlib.util, sys
        mod_path = BASE_DIR / "gpt_analyze.py"
        spec = importlib.util.spec_from_file_location("gpt_analyze", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)  # type: ignore
        log.info("gpt_analyze loaded (direct): %s", mod_path)
        return mod
    except Exception:
        log.exception("failed to load gpt_analyze")
        return None

async def _call_analyze(mod, body: Dict[str,Any], lang: str) -> Dict[str, Any]:
    """Ruft analyze_briefing async oder sync auf, robust gegen Fehlkonfigurationen."""
    # 1) Bevorzugt async analyze_briefing
    fn = getattr(mod, "analyze_briefing", None)
    if fn:
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(body, lang=lang)
            # sync → in eigenem Thread nicht blocken: trotzdem ok (keine inneren Loops!)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(body, lang=lang))
        except Exception:
            log.exception("analyze_briefing failed")
            raise

    # 2) Alternativ analyze (legacy)
    fn2 = getattr(mod, "analyze", None)
    if fn2:
        # Falls jemand noch eine sync analyze(data) bereitstellt
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn2(body, lang=lang))
        except Exception:
            log.exception("legacy analyze failed")
            raise

    raise RuntimeError("No analyze_briefing/analyze in gpt_analyze.py found")

# ---------- Jinja Render ----------
def _render_template_file(lang: str, ctx: Dict[str,Any]) -> str:
    tpl_name = "pdf_template_en.html" if lang.lower().startswith("en") else "pdf_template.html"
    tpl = env.get_template(tpl_name)

    # Meta-Defaults (Crash-Fix: meta.date)
    meta_defaults = {
        "title": "KI‑Statusbericht" if lang.startswith("de") else "AI Status Report",
        "date": dt.date.today().isoformat(),
        "lang": lang,
    }
    ctx = dict(ctx or {})
    ctx["meta"] = {**meta_defaults, **(ctx.get("meta") or {})}

    # Sicherheitsnetz: falls sections fehlen
    if not ctx.get("sections"):
        ctx["sections"] = [{"id":"empty","title":"Executive Summary","html":"<p>Report konnte nicht generiert werden. Es wurde ein narrativer Fallback eingeblendet.</p>"}]

    # Tabellen optional
    ctx["tables"] = ctx.get("tables") or {}

    return tpl.render(**ctx, now=dt.datetime.now)

async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    """Steuert den gesamten Analyze-Flow mit robusten Fallbacks."""
    mod = _load_analyze_module()
    if not mod:
        log.error("gpt_analyze not loaded; using bare template fallback")
        return _render_template_file(lang, {"sections":[]})

    try:
        result = await _call_analyze(mod, body, lang)
        # Erwartete Struktur: {"meta":..., "sections":[...], "tables":{...}}
        if not isinstance(result, dict) or "sections" not in result:
            log.error("analyze result invalid; using fallback")
            return _render_template_file(lang, {"sections":[]})

        # Sanity: Mindestinhalt
        html = _render_template_file(lang, result)
        if not html or len(html) < 1000:
            log.warning("HTML too short; injecting narrative fallback")
            fb = {"meta": result.get("meta", {}), "sections":[{"id":"fb","title":"Executive Summary","html":"<p>Kurzfassung: Die Analyse lieferte zu wenige Inhalte. Wir haben den Fallback aktiviert.</p>"}]}
            return _render_template_file(lang, fb)
        return html

    except Exception as e:
        log.exception("analyze_to_html failed: %s", e)
        return _render_template_file(lang, {"sections":[]})

# ---------- API ----------

@app.post("/api/login")
async def login(request: Request):
    # Dummy-Endpoint: euer bestehender bleibt gültig. Hier 200 OK zur Kompatibilität.
    return JSONResponse({"ok": True})

@app.post("/briefing_async")
async def briefing_async(request: Request):
    body = await request.json()
    lang = (body.get("lang") or "de").lower()
    rid = os.urandom(16).hex()

    # Warmup PDF
    await warmup_pdf_service(rid)

    # Analyse → HTML
    html = await analyze_to_html(body, lang)

    # PDF erzeugen (optional; hier wird nur der Status geloggt)
    pdf = await send_html_to_pdf_service(html, rid)
    if pdf is None:
        # Antwort bleibt 200 – Frontend erwartet nur "läuft"
        return JSONResponse({"ok": True, "rid": rid, "pdf": False})
    # In eurer produktiven Version würdet ihr PDF mailen/ablegen. Hier nur OK.
    return JSONResponse({"ok": True, "rid": rid, "pdf": True})
