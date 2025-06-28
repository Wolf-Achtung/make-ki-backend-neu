FROM python:3.11

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]
