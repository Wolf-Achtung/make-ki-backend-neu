# perplexity_client.py — resilient client (search-first) for Perplexity
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, time, random
import httpx

def _jitter(base: float, factor: float = 0.4) -> float:
    lo = base * (1.0 - factor)
    hi = base * (1.0 + factor)
    return random.uniform(lo, hi)

class PerplexityClient:
    def __init__(self, api_key: Optional[str] = None, timeout: float = 12.0, base_url: str = "https://api.perplexity.ai") -> None:
        self.api_key = (api_key or os.getenv("PERPLEXITY_API_KEY",""))
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # --- Internal HTTP helpers -------------------------------------------------
    def _post(self, path: str, payload: Dict[str,Any]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as c:
            return c.post(url, headers=headers, json=payload)

    def _backoff(self, attempt: int) -> None:
        # exponential with jitter; honor Retry-After if present (handled by caller)
        time.sleep(_jitter(0.6 * (2 ** attempt)))

    # --- Public API ------------------------------------------------------------
    def search(self, query: str, max_results: int = 8, include_domains: Optional[List[str]] = None, exclude_domains: Optional[List[str]] = None, days: Optional[int] = None) -> List[Dict[str,Any]]:
        if not self.api_key:
            return []
        include_domains = include_domains or []
        exclude_domains = exclude_domains or []
        # Prefer Search API – model-less; avoids invalid model errors.
        payload: Dict[str,Any] = {"q": query, "top_k": max_results}
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        if days:
            payload["days"] = int(days)

        # Try /search first; if 404, fall back to /v1/search (older docs).
        paths = ["/search", "/v1/search"]
        for path in paths:
            for attempt in range(0, 3):
                r = self._post(path, payload)
                if r.status_code == 200:
                    data = r.json()
                    res = []
                    for it in data.get("results", []):
                        url = it.get("url") or ""
                        res.append({
                            "title": it.get("title") or url,
                            "url": url,
                            "domain": it.get("domain") or (url.split('/')[2] if '://' in url else ""),
                            "date": (it.get("published_at") or it.get("published_date") or it.get("date") or "")[:10],
                            "score": it.get("score") or 0.0,
                            "snippet": it.get("snippet") or it.get("content") or "",
                        })
                    return res
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    if ra:
                        try: time.sleep(float(ra))
                        except Exception: self._backoff(attempt)
                    else:
                        self._backoff(attempt)
                    continue
                if r.status_code >= 500:
                    self._backoff(attempt)
                    continue
                # if 4xx other than 429: break and try next path
                break

        # Optional chat fallback if a valid model is configured
        model = (os.getenv("PPLX_MODEL","")) or (os.getenv("PPLX_CHAT_MODEL",""))
        if not model or model.lower() in {"auto","best","default"}:
            return []
        chat_payload = {
            "model": model,
            "messages": [{"role": "user", "content": f"List the most relevant web sources for: {query}. Return titles and links only."}],
            "max_tokens": 512,
            "temperature": 0.0
        }
        for attempt in range(0, 2):
            r = self._post("/chat/completions", chat_payload)
            if r.status_code == 200:
                try:
                    txt = (r.json().get("choices")[0].get("message").get("content") or "")
                except Exception:
                    return []
                # naive link harvest
                items: List[Dict[str,Any]] = []
                for line in txt.splitlines():
                    line = line.strip(" -*•\t")
                    if not line: continue
                    # try markdown [title](url)
                    import re
                    m = re.search(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^\)]+)\)", line)
                    if m:
                        u = m.group("url")
                        items.append({"title": m.group("title"), "url": u, "domain": u.split('/')[2], "date": ""})
                        continue
                    # fallback: split by http
                    if "http" in line:
                        parts = line.split("http", 1)
                        u = "http" + parts[1].split()[0].strip("()[]{}.")
                        title = parts[0].strip("-:• ") or u
                        items.append({"title": title, "url": u, "domain": u.split('/')[2], "date": ""})
                return items[:max_results]
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                if ra:
                    try: time.sleep(float(ra))
                    except Exception: self._backoff(attempt)
                else:
                    self._backoff(attempt)
                continue
        return []