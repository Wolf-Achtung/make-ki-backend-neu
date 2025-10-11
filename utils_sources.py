
# utils_sources.py
# Gold-Standard+: Klassifizierung & Dedupe für Live-Suchergebnisse (News/Tools/Förderungen)
# PEP8-konform, ohne externe Abhängigkeiten.
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple
import re
from urllib.parse import urlparse

__all__ = [
    "normalize_url",
    "get_domain",
    "classify_source",
    "dedupe_items",
    "baseline_funding",
]

# ---- URL/Domain Utils --------------------------------------------------------

def normalize_url(url: str) -> str:
    """Normalize URL by stripping fragments and query parameters that often cause duplicates."""
    if not url:
        return ""
    try:
        parts = urlparse(url)
        netloc = parts.netloc.lower()
        path = re.sub(r"/+", "/", parts.path or "/")
        # Remove common tracking params from query
        clean = f"{parts.scheme}://{netloc}{path}".rstrip("/")
        return clean
    except Exception:
        return url.strip()


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


# ---- Heuristics & Allow-/Block-Lists ----------------------------------------

FUNDING_DOMAINS = {
    "foerderdatenbank.de", "zim.de", "dlr-pt.de",
    "bmbf.de", "bmwk.de", "ibb.de", "investitionsbank-berlin.de",
    "berlin.de", "berlin-partner.de", "zab-brandenburg.de",
    "nrwbank.de", "l-bank.de", "sachsen-anhalt.de",
    "efre.nrw.de", "easme.europa.eu", "euresearch.de",
}
TOOLS_HINT_DOMAINS = {
    "openai.com", "aleph-alpha.com", "deepl.com", "zapier.com",
    "make.com", "notion.so", "microsoft.com", "azure.microsoft.com",
    "aws.amazon.com", "cloud.google.com", "anthropic.com", "huggingface.co",
    "pipedrive.com", "airtable.com", "slack.com", "n8n.io", "github.com",
}
NEWS_HINT_DOMAINS = {
    "heise.de", "golem.de", "t3n.de", "computerwoche.de", "welt.de", "faz.net",
    "handelsblatt.com", "zeit.de", "tagesschau.de", "news.sap.com", "blog.google",
}

FUNDING_PATTERNS = re.compile(
    r"(förde|zuschuss|richtlinie|förderquote|antragsfrist|stichtag|projektträger|bewilligung|förderprogramm)",
    re.IGNORECASE | re.UNICODE,
)
TOOLS_PATTERNS = re.compile(
    r"(pricing|preise|docs|dokumentation|api|signup|produkt|produktseite|app|download|integratio|features)",
    re.IGNORECASE | re.UNICODE,
)
NEWS_PATTERNS = re.compile(
    r"(news|presse|aktuell|meldung|bericht|studie|leitfaden|magazin|blog)",
    re.IGNORECASE | re.UNICODE,
)


# ---- Baseline Förderprogramme (Bund + Berlin) -------------------------------

def baseline_funding(bundesland_code: str | None = None) -> List[Dict[str, Any]]:
    """Kuratierte Basisliste seriöser Programme (Bund/BE) als Fallback.
    *Hinweis:* Links & Inhalte dienen als Startpunkt; Details bitte immer auf Zielseite prüfen.
    """
    items: List[Dict[str, Any]] = [
        {
            "title": "ZIM – Zentrales Innovationsprogramm Mittelstand (neue Richtlinie)",
            "url": "https://www.zim.de/",
            "domain": "zim.de",
            "date": "",
            "provider": "baseline",
            "category": "funding",
            "note": "Bundesweit; FuE/Kooperationsprojekte; Zuschüsse gestaffelt."
        },
        {
            "title": "BMBF – KMU-innovativ: IKT (Projektträger DLR)",
            "url": "https://www.dlr-pt.de/",
            "domain": "dlr-pt.de",
            "date": "",
            "provider": "baseline",
            "category": "funding",
            "note": "Bundesweit; thematische Förderlinien, Calls mit Stichtagen."
        },
    ]
    if (bundesland_code or "").upper() == "BE":
        items += [
            {
                "title": "Pro FIT Berlin (IBB/Technologieförderung)",
                "url": "https://www.berlin.de/sen/wirtschaft/",
                "domain": "berlin.de",
                "date": "",
                "provider": "baseline",
                "category": "funding",
                "note": "Berlin; Varianten für Frühphase/Markteinführung; Zuschüsse u. Darlehen."
            },
            {
                "title": "Transfer BONUS (IBB)",
                "url": "https://www.ibb.de/",
                "domain": "ibb.de",
                "date": "",
                "provider": "baseline",
                "category": "funding",
                "note": "Berlin; Zuschuss für Wissens-/Technologietransfer."
            },
        ]
    return items


# ---- Klassifizierung ---------------------------------------------------------

def classify_source(item: Dict[str, Any], briefing: Dict[str, Any] | None = None) -> str:
    """Klassifiziert einen Treffer als 'funding' | 'tools' | 'news' | 'other'.
    Nutzt Domain-Hinweise + Textmuster + Kontext (Branche/Größe/Hauptleistung)."""
    title = (item.get("title") or "").strip()
    url = normalize_url(item.get("url") or "")
    domain = item.get("domain") or get_domain(url)

    text = " ".join([title, domain]).lower()

    # Domain-Heuristik
    if domain in FUNDING_DOMAINS or FUNDING_PATTERNS.search(text):
        return "funding"
    if domain in TOOLS_HINT_DOMAINS or TOOLS_PATTERNS.search(text):
        return "tools"
    if domain in NEWS_HINT_DOMAINS or NEWS_PATTERNS.search(text):
        return "news"

    # Kontext-Heuristik (z. B. Tools für die Hauptleistung)
    if briefing:
        haupt = (briefing.get("hauptleistung") or "").lower()
        branche = (briefing.get("branche_label") or briefing.get("branche") or "").lower()
        if any(k in text for k in ("preis", "pricing", "api", "signup", "features")) and any(
            k in text for k in (branche, haupt)
        ):
            return "tools"

    # Fallback: Nachrichten
    return "news"


def _norm_title(s: str) -> str:
    s = re.sub(r"\s+–\s*Tavily$", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).lower()
    return s


def dedupe_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupliziert nach (domain+title_norm) und (normalized_url)."""
    seen: set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        url = normalize_url(it.get("url") or "")
        dom = it.get("domain") or get_domain(url)
        title = _norm_title(it.get("title") or it.get("name") or it.get("url") or "")
        key = (dom, title) if title else (dom, url)
        if key in seen:
            continue
        seen.add(key)
        it["url"] = url
        it["domain"] = dom
        out.append(it)
    return out
