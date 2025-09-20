# SMOKE_POST_PDF.py — posts sample HTML to the PDF service if configured
import os
import gpt_analyze
from main import _post_pdfservice, PDF_SERVICE_URL, PDF_TIMEOUT

briefing = {"branche":"Beratung","unternehmensgroesse":"solo","standort":"Berlin","sprache":"de","email":os.getenv("TEST_USER_EMAIL","")}
ctx = gpt_analyze.build_context(briefing, "de")
html = gpt_analyze.render_html(ctx, "de")

if not PDF_SERVICE_URL:
    print("PDF_SERVICE_URL not set; skipping PDF post smoke test.")
else:
    status, body, headers = _post_pdfservice(PDF_SERVICE_URL, html, lang="de", to_email=briefing.get("email"), subject=os.getenv("PDF_SUBJECT","Ihr KI‑Status‑Report"), mode=os.getenv("PDF_POST_MODE","html"), timeout=PDF_TIMEOUT)
    print("status:", status)
    print("ctype:", headers.get("Content-Type") or headers.get("content-type"))
    if status == 200 and (headers.get("Content-Type") or headers.get("content-type") or "").lower().startswith("application/pdf"):
        open("smoke.pdf","wb").write(body)
        print("PDF written: smoke.pdf")
    else:
        open("debug.html","w",encoding="utf-8").write(html)
        print("Wrote debug.html")
