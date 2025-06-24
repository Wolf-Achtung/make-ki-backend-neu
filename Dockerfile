# Basis-Image
FROM python:3.11-slim

# Arbeitsverzeichnis
WORKDIR /app

# Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code
COPY . .

# Port für Railway
EXPOSE 8000

# Startbefehl für Production über gunicorn (anstatt python main.py)
CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]
