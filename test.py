import requests

data = {
    "branche": "Finanzen",
    "selbststaendig": "Ja",
    "massnahme": "KI-Tool",
    "bereich": "Marketing",
    "ziel": "Kosten senken",
    "ds_gvo": "Teilweise"
}
response = requests.post("http://localhost:8000/briefing", json=data)
print(response.json())