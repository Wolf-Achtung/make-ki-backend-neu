FROM python:3.11-slim

FROM python:3.11-slim

# Install system dependencies incl. wkhtmltopdf
RUN apt-get update && \
    apt-get install -y wkhtmltopdf curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
