import os
from serpapi import GoogleSearch

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

def serpapi_search(query, num_results=5):
    params = {
        "q": query,
        "location": "Germany",
        "hl": "de",
        "gl": "de",
        "api_key": SERPAPI_KEY,
        "num": num_results
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    links = []
    if "organic_results" in results:
        for item in results["organic_results"]:
            # HTML-Link (sauber formatiert für PDF/HTML-Report)
            links.append(f"<li><a href='{item['link']}' target='_blank'>{item['title']}</a></li>")
    return "<ul>" + "".join(links) + "</ul>"
