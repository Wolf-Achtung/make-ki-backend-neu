import json
import requests
from bs4 import BeautifulSoup

def check_sync():
    try:
        # Felder aus deiner neuen smarten fields.json laden
        with open("fields.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            expected_fields = set([field["name"] for field in data["fields"]])

        # HTML live von Netlify oder wo auch immer ziehen
        url = "https://make.ki-sicherheit.jetzt/formular/index.html"
        res = requests.get(url)
        res.raise_for_status()

        # Parse HTML und finde alle name="..." Attribute
        soup = BeautifulSoup(res.text, 'html.parser')
        html_fields = set(
            tag.get("name") 
            for tag in soup.find_all(["input", "select", "textarea"]) 
            if tag.get("name")
        )

        # Sets vergleichen
        missing_in_html = expected_fields - html_fields
        extra_in_html = html_fields - expected_fields

        return {
            "status": "ok" if not missing_in_html and not extra_in_html else "warn",
            "expected_fields": list(expected_fields),
            "found_in_html": list(html_fields),
            "missing_in_html": list(missing_in_html),
            "extra_in_html": list(extra_in_html)
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print(json.dumps(check_sync(), indent=2, ensure_ascii=False))
