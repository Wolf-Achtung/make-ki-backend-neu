import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_analysis(user_input):
    prompt = f"""Erstelle eine strukturierte Analyse für folgende Nutzereingabe:
{user_input}"

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return {
        "prompt": prompt,
        "response": response.choices[0].message.content.strip()
    }
"""
