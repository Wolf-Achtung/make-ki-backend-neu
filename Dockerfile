
# Basis-Image
FROM python:3.11-slim

# Arbeitsverzeichnis
WORKDIR /app

# Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code
COPY . .

# Port (optional, meist für lokale Tests)
EXPOSE 8000

# Startbefehl für Flask
CMD ["python", "main.py"]
