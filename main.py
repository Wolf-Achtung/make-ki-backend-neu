# main.py — robust FastAPI app for rendering HTML and posting to PDF service
import os, json, logging, importlib, urllib.request, urllib.error
from typing import Any, Dict
from pathlib import Path
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, Response

import gpt_analyze

LOG = logging.getLogger("app")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "").rstrip("/")
PDF_TIMEOUT = float(os.getenv("PDF_TIMEOUT", "120"))
TEMPLATE_DIR = os.getenv("TEMPLATE_DIR", "templates")

app = FastAPI(title="KI-Status-Report Backend", version=getattr(gpt_analyze, "__VERSION__", "dev"))

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
    return f"<html><body><h1>KI‑Statusbericht</h1><p>Fallback aktiv: {reason}</p></body></html>"

def load_analyze_module():
    try:
        importlib.reload(gpt_analyze)
        LOG.info("Analyze module loaded: %s", getattr(gpt_analyze, "__VERSION__", "?"))
        return True, ""
    except Exception as e:
        LOG.exception("Analyze module failed to load: %s", e)
        return False, str(e)

def _post_pdfservice(url: str, html: str, lang: str = "de", to_email: str | None = None, subject: str | None = None, mode: str = "html", timeout: float = 120.0):
    req_url = url.rstrip("/") + "/generate-pdf"
    headers = {
        "X-Request-ID": os.getenv("REQUEST_ID", ""),
        "X-Lang": lang or "de",
    }
    if to_email:
        headers["X-User-Email"] = to_email
    if subject:
        headers["X-Subject"] = subject

    if mode == "json":
        payload = json.dumps({"html": html, "lang": lang, "to": to_email, "subject": subject or ""}, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
        data = payload
    else:
        data = (html or "").encode("utf-8")
        headers["Content-Type"] = "text/html; charset=utf-8"

    req = urllib.request.Request(req_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(), dict(resp.getheaders())
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b"", dict(e.headers or {})
    except Exception as e:
        LOG.exception("PDF service call failed: %s", e)
        return 0, b"", {}

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
        elif mode == "pdf":
            to_email = (briefing.get("email") or briefing.get("kontakt_email") or briefing.get("user_email") or "") if isinstance(briefing, dict) else ""
            subject = os.getenv("PDF_SUBJECT", "Ihr KI‑Status‑Report")
            post_mode = os.getenv("PDF_POST_MODE", "html").lower()
            if not PDF_SERVICE_URL:
                LOG.warning("PDF_SERVICE_URL not set; returning HTML instead")
                return HTMLResponse(html)
            status, body_bytes, headers = _post_pdfservice(PDF_SERVICE_URL, html, lang=(lang if lang in ("de","en") else "de"), to_email=to_email, subject=subject, mode=post_mode, timeout=PDF_TIMEOUT)
            ctype = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
            if status == 200 and ctype.startswith("application/pdf"):
                return Response(content=body_bytes, media_type="application/pdf", headers={k:v for k,v in headers.items() if k.lower().startswith("x-")})
            else:
                LOG.error("PDF service error: status=%s, content-type=%s", status, ctype)
                return HTMLResponse(html)
        else:
            return HTMLResponse(html)
    except Exception as e:
        LOG.exception("Render failed: %s", e)
        return HTMLResponse(_fallback_html("Render-Fehler: "+str(e)))

if __name__ == "__main__":
    try:
        import uvicorn  # type: ignore
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    except Exception as e:
        print("Uvicorn start skipped:", e)
