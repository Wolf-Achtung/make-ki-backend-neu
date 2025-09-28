FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y sed && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN sed -i 's/now().year/2025/g' /app/templates/*.html 2>/dev/null || true && \
    sed -i 's/ddefault/default/g' /app/templates/*.html 2>/dev/null || true && \
    mkdir -p /app/prompts
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]