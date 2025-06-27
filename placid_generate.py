
import os
import requests
from dotenv import load_dotenv

load_dotenv()

PLACID_API_KEY = os.getenv("PLACID_API_KEY")
PLACID_TEMPLATE_ID = os.getenv("PLACID_TEMPLATE_ID")

def generate_placid_pdf(data):
    headers = {
        "Authorization": f"Bearer {PLACID_API_KEY}",
        "Content-Type": "application/json"
    }

    content = {
        "name": data.get("name", ""),
        "unternehmen": data.get("unternehmen", ""),
        "email": data.get("email", ""),
        "branche": data.get("branche", ""),
        "score": data.get("score", ""),
        "status": data.get("status", ""),
        "executive_summary": data.get("executive_summary", ""),
        "foerdertipps": data.get("foerdertipps", ""),
        "toolkompass": data.get("toolkompass", ""),
        "branche_trend": data.get("branche_trend", ""),
        "compliance": data.get("compliance", ""),
        "beratungsempfehlung": data.get("beratungsempfehlung", ""),
        "vision": data.get("vision", ""),
        "ziel": data.get("ziel", ""),
        "herausforderung": data.get("herausforderung", "")
    }

    payload = {
        "template": PLACID_TEMPLATE_ID,
        "format": "pdf",
        "data": {
            "html": render_html(content)
        }
    }

    response = requests.post("https://api.placid.app/api/rest/graphics", headers=headers, json=payload)

    if response.status_code == 200:
        result = response.json()
        return result.get("url")
    else:
        raise Exception(f"Placid API error: {response.status_code} – {response.text}")


def render_html(data):
    return f"""
    <div style='font-family:Arial, sans-serif; font-size:14px; color:#003366;'>
        <h1>KI-Briefing</h1>
        <p><strong>Name:</strong> {data["name"]}<br/>
        <strong>Unternehmen:</strong> {data["unternehmen"]}<br/>
        <strong>E-Mail:</strong> {data["email"]}<br/>
        <strong>Branche:</strong> {data["branche"]}<br/>
        <strong>Score:</strong> {data["score"]} – Status: {data["status"]}</p>

        <h2>Executive Summary</h2>
        <p>{data["executive_summary"]}</p>

        <h2>Fördertipps</h2>
        <p>{data["foerdertipps"]}</p>

        <h2>Toolkompass</h2>
        <p>{data["toolkompass"]}</p>

        <h2>Branche & Trends</h2>
        <p>{data["branche_trend"]}</p>

        <h2>Compliance & Risiko</h2>
        <p>{data["compliance"]}</p>

        <h2>Beratungsempfehlung</h2>
        <p>{data["beratungsempfehlung"]}</p>

        <h2>Visionärer Ausblick</h2>
        <p>{data["vision"]}</p>

        <h2>Ihr Ziel mit KI</h2>
        <p>{data["ziel"]}</p>

        <h2>Ihre größte Herausforderung</h2>
        <p>{data["herausforderung"]}</p>
    </div>
    """
