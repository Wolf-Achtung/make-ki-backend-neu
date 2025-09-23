from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from services import data_loader, rendering, news, i18n
from gpt_analyze import build_report_payload

router = APIRouter()

class ReportRequest(BaseModel):
    language: str = Field(default="de", description="de oder en")
    company: Optional[str] = None
    industry: Optional[str] = None
    include_news: bool = True
    sections: Optional[List[str]] = Field(default=None, description="Falls nur bestimmte Abschnitte gerendert werden sollen")
    format: str = Field(default="html", description="html oder pdf")
    template_name: Optional[str] = Field(default=None, description="Optional explizite Template-Datei, sonst auto je Sprache")

class ReportResponse(BaseModel):
    language: str
    meta: Dict[str, Any]
    html: Optional[str] = None
    pdf_path: Optional[str] = None

@router.post("/report", response_model=ReportResponse)
def generate_report(req: ReportRequest):
    lang = i18n.normalize_lang(req.language)
    if lang not in ("de", "en"):
        raise HTTPException(status_code=400, detail="language must be de or en")

    # Load prompts & data (robust)
    prompts = data_loader.load_all_prompts(lang)
    datasets = data_loader.load_all_data()

    # Optionally add news via Tavily
    latest_news = []
    if req.include_news:
        latest_news = news.fetch_news(company=req.company, industry=req.industry, language=lang)

    # Build content payload (can use LLM if configured)
    payload = build_report_payload(
        language=lang,
        company=req.company,
        industry=req.industry,
        prompts=prompts,
        datasets=datasets,
        latest_news=latest_news,
        sections=req.sections
    )

    # Render to HTML (and maybe PDF)
    template = req.template_name or ("report_template_de.html" if lang == "de" else "report_template_en.html")

    html = rendering.render_html(template_name=template, context=payload)
    meta = {"template": template, "has_news": bool(latest_news), "sections": list(payload.get("sections", {}).keys())}

    if req.format == "pdf":
        pdf_path = rendering.render_pdf_from_html(html, language=lang)
        return ReportResponse(language=lang, meta=meta, pdf_path=pdf_path)
    else:
        return ReportResponse(language=lang, meta=meta, html=html)
