# websearch_utils.py — Live Updates via Tavily (Gold-Standard+)
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx

LOG = os.getenv("LOG_LEVEL", "INFO").upper() != "ERROR"
CACHE_PATH = os.getenv("TAVILY_CACHE_FILE", "/tmp/tavily_cache.json")
CACHE_TTL = int(os.getenv("TAVILY_CACHE_TTL", "21600"))  # Sekunden (default 6h)

def _now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _domain(url: str) -> str:
    try:
        return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    except Exception:
        return ""

def _read_cache() -> Dict[str, Any]:
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _write_cache(data: Dict[str, Any]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def _cache_get(key: str) -> Optional[Any]:
    data = _read_cache()
    v = data.get(key)
    if not v:
        return None
    ts = v.get("_ts", 0)
    if (dt.datetime.utcnow().timestamp() - ts) > CACHE_TTL:
        return None
    return v.get("payload")

def _cache_set(key: str, payload: Any) -> None:
    data = _read_cache()
    data[key] = {"_ts": dt.datetime.utcnow().timestamp(), "payload": payload}
    _write_cache(data)

def _tv_search(
    query: str,
    days: int,
    max_results: int,
    include_domains: List[str],
    exclude_domains: List[str],
    *,
    topic: Optional[str] = None,
    time_range: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Führe eine Suche über die Tavily‑API aus. Dieses Hilfsmodul kapselt
    sämtliche Parameter und sorgt für robuste Standardwerte. Es werden
    unnötige Felder entfernt, wenn sie nicht gesetzt sind, und sensible
    Header wie "Authorization" nur optional hinzugefügt. Falls ein
    ``topic`` angegeben ist, wird ``days`` nur beim Topic ``news``
    verwendet, andernfalls wird ein ``time_range`` aus den Tagen
    generiert. ``include_answer`` und ``include_raw_content`` sind
    standardmäßig deaktiviert. Durch das Argument ``language`` kann
    optional die Sprache übergeben werden (falls von Tavily unterstützt).

    Bei HTTP‑Fehlern oder fehlgeschlagenen Requests wird eine leere
    Liste zurückgegeben. Der Rückgabewert ist auf ``max_results``
    begrenzt.
    """

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []

    # Basispayload definieren
    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }

    # include/exclude nur setzen, wenn Listen nicht leer sind
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    # Sprache (optional)
    if language:
        payload["language"] = language

    # Topic‑spezifische Logik: news → days
    if topic:
        payload["topic"] = topic
        if topic == "news":
            payload["days"] = max(1, int(days))

    # Zeitfenster bestimmen
    if time_range:
        payload["time_range"] = time_range
    elif not topic or topic != "news":
        # Wenn weder time_range noch topic=news gesetzt ist, days in time_range mappen
        d = max(1, int(days))
        if d <= 1:
            tr = "day"
        elif d <= 7:
            tr = "week"
        elif d <= 31:
            tr = "month"
        else:
            tr = "year"
        payload["time_range"] = tr

    # Optionaler Bearer‑Header, falls gefordert
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if os.getenv("TAVILY_USE_BEARER", "0").lower() in {"1", "true", "yes"}:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=httpx.Timeout(20.0)) as cli:
            r = cli.post(
                "https://api.tavily.com/search",
                json=payload,
                headers=headers,
            )
            if r.status_code != 200:
                if LOG:
                    try:
                        detail = r.text[:500]
                    except Exception:
                        detail = "<no-body>"
                    print(
                        f"[tavily] HTTP {r.status_code} for query='{query}': {detail}"
                    )
                return []
            data = r.json()
            results = data.get("results") or []
            if not isinstance(results, list):
                return []
            return results[:max_results]
    except Exception as e:
        if LOG:
            print(f"[tavily] request failed: {e}")
        return []

def _cards(items: List[Dict[str, Any]], title_de: str, title_en: str, lang: str) -> str:
    if not items:
        return ""
    title = title_de if lang.startswith("de") else title_en
    rows = []
    for it in items:
        url = it.get("url") or it.get("link") or ""
        t = html.escape(it.get("title") or it.get("name") or _domain(url))
        s = html.escape(it.get("content") or it.get("snippet") or "")
        dom = _domain(url)
        date = it.get("published_date") or it.get("date") or ""
        if date:
            date = html.escape(str(date)[:10])
        a = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{t}</a>'
        meta = f"{date} · {dom}" if date else dom
        rows.append(f'<div class="live-card"><div class="live-title">{a}</div><div class="live-meta">{meta}</div><div class="live-snippet">{s}</div></div>')
    return f'<div class="live-group"><div class="live-title-group">{title}</div>{"".join(rows)}</div>'

def collect_recent_items(ctx: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
    """
    Liefert HTML-Blöcke für die Kategorien Nachrichten, Tools, Förderungen und Deadlines.
    Die Suche verwendet die Tavily-API mit anpassbaren Parametern. Der Suchbegriff
    wird dynamisch aus Branche, Hauptleistung und Bundesland zusammengesetzt, um
    relevantere Treffer zu erzielen. Cache wird genutzt, um Anfragen zu reduzieren.
    """

    # Konfiguration aus der Umgebung lesen
    days = int(os.getenv("SEARCH_DAYS", "14"))
    days_tools = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
    days_funding = int(os.getenv("SEARCH_DAYS_FUNDING", "30"))
    max_results = int(os.getenv("SEARCH_MAX_RESULTS", "7"))
    live_max = int(os.getenv("LIVE_NEWS_MAX", "5"))
    include_domains = [d.strip() for d in os.getenv("SEARCH_INCLUDE_DOMAINS", "").split(",") if d.strip()]
    exclude_domains = [d.strip() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS", "").split(",") if d.strip()]

    out: Dict[str, str] = {}
    # Bestimme Branchenschlagwort und Hauptleistung (Freitext)
    branche = str(ctx.get("branche") or "").strip()
    haupt = str(ctx.get("hauptleistung") or "").strip()
    # Kombiniere Branchenschlagwort und Hauptleistung (falls beide vorhanden)
    company_topic = " ".join([x for x in [branche, haupt] if x]).strip() or "KI Mittelstand"
    # Bestimme Bundeslandname aus Kürzel
    region_code = str(ctx.get("bundesland", "")).upper()
    region_map = {
        "BE": "Berlin", "BY": "Bayern", "BW": "Baden-Württemberg", "NW": "Nordrhein-Westfalen", "HE": "Hessen",
        "RP": "Rheinland-Pfalz", "SL": "Saarland", "SN": "Sachsen", "TH": "Thüringen", "HB": "Bremen",
        "HH": "Hamburg", "MV": "Mecklenburg-Vorpommern", "NI": "Niedersachsen", "SH": "Schleswig-Holstein",
        "ST": "Sachsen-Anhalt", "BB": "Brandenburg"
    }
    region_name = region_map.get(region_code, "Deutschland")
    # Sprache bestimmen
    if lang.lower().startswith("de"):
        language_param = "de"
        news_query = f"{company_topic} {region_name} KI News"
        tools_query = f"{company_topic} {region_name} KI Tools"
        funding_query = f"{company_topic} {region_name} Förderprogramme"
        deadlines_query = f"{company_topic} {region_name} Förderfrist"
    else:
        language_param = "en"
        news_query = f"{company_topic} {region_name} AI News"
        tools_query = f"{company_topic} {region_name} AI tools"
        funding_query = f"{company_topic} {region_name} funding grants"
        deadlines_query = f"{company_topic} {region_name} grant deadline"

    # Nachrichten (topic=news)
    if os.getenv("SHOW_REGWATCH", "1").lower() in {"1", "true", "yes"}:
        key = f"news:{company_topic}:{region_name}:{days}:{max_results}:{language_param}"
        news = _cache_get(key)
        if news is None:
            news = _tv_search(
                news_query,
                days,
                max_results,
                include_domains,
                exclude_domains,
                topic="news",
                language=language_param,
            )[:live_max]
            _cache_set(key, news)
        out["news_html"] = _cards(news, "Aktuelle Meldungen", "Recent updates", lang)

    # Neue Tools & Releases
    if os.getenv("SHOW_TOOLS_NEWS", "1").lower() in {"1", "true", "yes"}:
        key = f"tools:{company_topic}:{region_name}:{days_tools}:{max_results}:{language_param}"
        tools = _cache_get(key)
        if tools is None:
            tools = _tv_search(
                tools_query,
                days_tools,
                max_results,
                include_domains,
                exclude_domains,
                language=language_param,
            )[:live_max]
            _cache_set(key, tools)
        out["tools_rich_html"] = _cards(tools, "Neue Tools & Releases", "New tools & releases", lang)

    # Förderprogramme
    if os.getenv("SHOW_FUNDING_STATUS", "1").lower() in {"1", "true", "yes"}:
        key = f"funding:{company_topic}:{region_name}:{days_funding}:{max_results}:{language_param}"
        fund = _cache_get(key)
        if fund is None:
            fund = _tv_search(
                funding_query,
                days_funding,
                max_results,
                include_domains,
                exclude_domains,
                language=language_param,
            )[:live_max]
            _cache_set(key, fund)
        out["funding_rich_html"] = _cards(fund, "Förderprogramme & Ausschreibungen", "Funding & grants", lang)

    # Deadlines
    if os.getenv("SHOW_FUNDING_DEADLINES", "1").lower() in {"1", "true", "yes"}:
        key = f"deadlines:{company_topic}:{region_name}:{days_funding}:{max_results}:{language_param}"
        dls = _cache_get(key)
        if dls is None:
            dls = _tv_search(
                deadlines_query,
                days_funding,
                max_results,
                include_domains,
                exclude_domains,
                language=language_param,
            )[:live_max]
            _cache_set(key, dls)
        out["funding_deadlines_html"] = _cards(dls, "Fristen & Deadlines", "Deadlines", lang)

    return out
