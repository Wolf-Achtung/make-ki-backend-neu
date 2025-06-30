import json
import requests
from bs4 import BeautifulSoup

def check_sync():
    try:
        # Felder aus fields.json laden
        with open("fields.json", "r") as f:
            fields = json.load(f)

        # HTML-Datei aus Netlify laden
        url = "https://make.ki-sicherheit.jetzt/formular/index.html"
        res = requests.get(url)
        res.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(res.text, 'html.parser')
        html_fields = set([tag.get("name") for tag in soup.find_all(["input", "select"]) if tag.get("name")])

        # Check
        expected_fields = set(fields)
        missing_in_html = expected_fields - html_fields
        extra_in_html = html_fields - expected_fields

        return {
            "status": "ok",
            "expected_fields": list(expected_fields),
            "found_in_html": list(html_fields),
            "missing_in_html": list(missing_in_html),
            "extra_in_html": list(extra_in_html)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
