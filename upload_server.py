
from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

@app.route('/upload-template', methods=['POST'])
def upload_template():
    file = request.files.get('htmlFile')
    if not file:
        return jsonify({'error': 'Keine Datei ausgewählt'}), 400

    html_content = file.read().decode('utf-8')
    api_key = os.getenv("PLACID_API_KEY")
    template_id = os.getenv("PLACID_TEMPLATE_ID")

    if not api_key or not template_id:
        return jsonify({'error': 'API Key oder Template ID fehlt in den Umgebungsvariablen.'}), 500

    response = requests.put(
        f"https://api.placid.app/api/rest/templates/{template_id}/html",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"html": html_content}
    )

    if response.status_code == 200:
        return "✅ Template erfolgreich aktualisiert!"
    else:
        return f"❌ Fehler: {response.status_code} – {response.text}", 500

if __name__ == '__main__':
    app.run(debug=True)
