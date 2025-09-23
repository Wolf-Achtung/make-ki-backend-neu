from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from services.config import settings

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=False
)

def render_html(template_name: str, context: Dict[str, Any]) -> str:
    template = env.get_template(template_name)
    # inject CSS
    css = (ROOT / 'assets' / 'styles.css').read_text(encoding='utf-8') if (ROOT / 'assets' / 'styles.css').exists() else ''
    context = dict(context)
    context.setdefault('styles', css)
    return template.render(**context)

def render_pdf_from_html(html: str, language: str = "de") -> str:
    """
    We use WeasyPrint (pure-Python) to render PDFs.
    On some systems, extra system libraries are required. If WeasyPrint
    is not available, we raise a runtime error.
    """
    if not settings.ENABLE_PDF:
        raise RuntimeError("PDF rendering disabled via ENABLE_PDF=false")

    try:
        from weasyprint import HTML  # type: ignore
    except Exception as e:
        raise RuntimeError(f"WeasyPrint not installed or missing system libs: {e}") from e

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"report_{language}.pdf"
    HTML(string=html).write_pdf(str(out_path))
    logger.info(f"PDF created at {out_path}")
    return str(out_path)
