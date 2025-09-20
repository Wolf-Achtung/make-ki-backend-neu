# main.py — minimal robust FastAPI app for rendering the report
import os, json, logging
from typing import Any, Dict
from pathlib import Path
from datetime import datetime as dt

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

import importlib

# Local analyze module
import gpt_analyze

LOG = logging.getLogger("app")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT", "120"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", "templates")

app = FastAPI(title="KI-Status-Report Backend", version=getattr(gpt_analyze, "__VERSION__", "dev"))

# CORS (allow all by default)
origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")]
if origins == ["*"]:
    origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _safe_len_html(html: str) -> int:
    return len((html or "").strip())

def _fallback_html(reason: str) -> str:
    # simple, printable fallback in case templates or context fail
    return f"<html><body><h1>KI‑Statusbericht</h1><p>Fallback aktiv: {reason}</p></body></html>"

def load_analyze_module():
    try:
        importlib.reload(gpt_analyze)
        LOG.info("Analyze module loaded OK: %s", getattr(gpt_analyze, "__VERSION__", "?"))
        return True, ""
    except Exception as e:
        LOG.exception("Analyze module failed to load: %s", e)
        return False, str(e)

@app.get("/health")
def health():
    ok, err = load_analyze_module()
    status = "ok" if ok else f"error: {err}"
    return JSONResponse({"status": status, "version": getattr(gpt_analyze, "__VERSION__", "dev")})

@app.post("/render")
def render(
    briefing: Dict[str, Any] = Body(..., embed=True),
    lang: str = Body("de"),
    mode: str = Body("html"),
):
    """
    Render the report as HTML (default). If mode='pdf' and a PDF service is configured,
    you can forward the HTML there (implementation stub).
    """
    ok, err = load_analyze_module()
    if not ok:
        html = _fallback_html("Analyze-Modul konnte nicht geladen werden")
        return HTMLResponse(html)

    lang = (lang or "de").lower()
    if lang not in ("de", "en", "both"):
        lang = "de"

    try:
        ctx_de = gpt_analyze.build_context(briefing, "de")
        html_de = gpt_analyze.render_html(ctx_de, "de")
        html = html_de

        if lang == "en":
            ctx_en = gpt_analyze.build_context(briefing, "en")
            html = gpt_analyze.render_html(ctx_en, "en")
        elif lang == "both":
            ctx_en = gpt_analyze.build_context(briefing, "en")
            html_en = gpt_analyze.render_html(ctx_en, "en")
            html = html_de + '<div style="page-break-before:always"></div>' + html_en

        if _safe_len_html(html) < 1000:
            html = _fallback_html("HTML zu kurz (<1000 Zeichen) – Fallback aktiv")

        if mode == "html":
            return HTMLResponse(html)
        else:
            # Optional: forward to PDF service (not implemented here)
            return HTMLResponse(html)  # keep behaviour consistent
    except Exception as e:
        LOG.exception("Render failed: %s", e)
        return HTMLResponse(_fallback_html("Render-Fehler: "+str(e)))

if __name__ == "__main__":
    try:
        import uvicorn  # type: ignore
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    except Exception as e:
        print("Uvicorn start skipped:", e)
