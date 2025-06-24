import os
import json
from openai import OpenAI

client = OpenAI()


def get_analysis(data):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher Assistent für KI-Checks."},
            {"role": "user", "content": f"Analysiere bitte diese Eingabedaten: {json.dumps(data, ensure_ascii=False)}"}
        ]
    )
    return response.choices[0].message.content.strip()
