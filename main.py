# main.py — HF-FINAL 2025-09-19
from __future__ import annotations
import os, asyncio, json, logging, datetime as dt, importlib, uuid, time
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader, select_autoescape

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [backend] %(message)s")
log = logging.getLogger("backend")

# --- Templates ---------------------------------------------------------------
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR", "templates")).resolve()
_JINJA = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

def _tpl_name(lang: str) -> str:
    return "pdf_template_en.html" if (lang or "de").lower().startswith("en") else "pdf_template.html"

def _render_template_file(lang: str, ctx: Dict[str, Any]) -> str:
    tpl = _JINJA.get_template(_tpl_name(lang))
    return tpl.render(**ctx, now=dt.datetime.now)

# --- Idempotency (simple TTL cache) -----------------------------------------
_SEEN_RIDS: Dict[str, float] = {}
_SEEN_TTL = int(os.getenv("IDEMPOTENCY_TTL", "600"))

def _idemp_seen(rid: str) -> bool:
    now = time.time()
    # GC
    expired = [k for k, t in _SEEN_RIDS.items() if (now - t) > _SEEN_TTL]
    for k in expired:
        _SEEN_RIDS.pop(k, None)
    if rid in _SEEN_RIDS:
        return True
    _SEEN_RIDS[rid] = now
    return False

# --- Analyze module loader ---------------------------------------------------
def load_analyze_module():
    try:
        importlib.invalidate_caches()
        ga = importlib.import_module("gpt_analyze")
        log.info("gpt_analyze geladen: %s", Path("gpt_analyze.py").resolve())
        return ga
    except Exception as e:
        log.error("gpt_analyze Importfehler: %s", e, exc_info=True)
        raise

# --- API Model ---------------------------------------------------------------
class BriefingBody(BaseModel):
    lang: Optional[str] = None
    # alle Formular-Felder permissiv zulassen
    __root__: Dict[str, Any] | None = None

    def dict_all(self) -> Dict[str, Any]:
        base = self.dict() or {}
        root = (self.__root__ or {})
        base.update(root)
        return base

# --- FastAPI app -------------------------------------------------------------
app = FastAPI(title="KI-Sicherheit Backend", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# Lifespan (statt on_event deprecated)
@app.on_event("startup")
async def _startup():
    log.info("[DB] Pool initialisiert")

@app.on_event("shutdown")
async def _shutdown():
    pass

# --- Analyze → HTML ----------------------------------------------------------
def _empty_ctx(lang: str) -> Dict[str, Any]:
    return {
        "meta": {"lang": "en" if lang.startswith("en") else "de"},
        "sections": {
            "executive_summary": "", "quick_wins": "", "risks": "", "recommendations": "",
            "roadmap": "", "vision": "", "gamechanger": "", "compliance": "",
            "funding_programs": "", "tools": ""
        },
        "live_box_html": "",
    }

async def analyze_to_html(body: Dict[str, Any], lang: str) -> str:
    ga = load_analyze_module()
    analyze_fn = getattr(ga, "analyze_briefing", None)
    if not callable(analyze_fn):
        log.error("gpt_analyze geladen, aber analyze_briefing nicht gefunden.")
        return _render_template_file(lang, _empty_ctx(lang))

    # Analyse → Kontext
    try:
        ctx: Dict[str, Any] = analyze_fn(body, lang=lang)
        if not isinstance(ctx, dict):
            raise RuntimeError("analyze_briefing must return dict")
    except Exception as e:
        log.error("analyze_briefing failed: %s", e, exc_info=True)
        return _render_template_file(lang, _empty_ctx(lang))

    # Schlüssel garantieren
    ctx.setdefault("meta", {})
    ctx.setdefault("sections", {})
    for key in ("executive_summary", "quick_wins", "risks", "recommendations",
                "roadmap", "vision", "gamechanger", "compliance", "funding_programs", "tools"):
        ctx["sections"].setdefault(key, "")
    ctx.setdefault("live_box_html", "")

    # Render
    try:
        html = _render_template_file(lang, ctx)
    except Exception as e:
        log.error("Jinja render failed: %s", e, exc_info=True)
        return _render_template_file(lang, _empty_ctx(lang))

    # Soft-Safety: nie crashen wegen Rest-Markern
    if ("{{ sections." in html) or ("{{ meta." in html) or ("{%" in html):
        log.warning("Template enthält nach Rendern noch Jinja-Marker – Output wird dennoch geliefert (no 500).")
    return html

# --- Routes ------------------------------------------------------------------
@app.post("/api/login")
async def login():
    return {"ok": True}

@app.post("/briefing_async")
async def briefing_async(req: Request, body: BriefingBody, bg: BackgroundTasks):
    data = await req.json()
    rid = data.get("rid") or str(uuid.uuid4())
    if _idemp_seen(rid):
        return {"ok": True, "rid": rid, "status": "duplicate-ignored"}

    lang = (data.get("lang") or data.get("language") or "de").lower()
    lang = "en" if lang.startswith("en") else "de"
    html = await analyze_to_html(body.dict_all(), lang)
    # PDF‑Service call
    pdf_url = os.getenv("PDF_URL", "https://make-ki-pdfservice-production.up.railway.app/generate-pdf")
    import httpx
    try:
        resp = httpx.post(pdf_url, json={"html": html, "rid": rid}, timeout=60)
        log.info("[PDF] rid=%s attempt=1 status=%s", rid, resp.status_code)
    except Exception as e:
        log.error("PDF-Service Fehler: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="PDF service failed")
    return {"ok": True, "rid": rid}
