import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import pdfkit
import boto3
from botocore.exceptions import NoCredentialsError

# AWS Config aus Environment Variablen
aws_region = os.getenv("AWS_DEFAULT_REGION")
bucket_name = os.getenv("AWS_S3_BUCKET")

s3_client = boto3.client(
    's3',
    region_name=aws_region,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

def create_pdf_and_upload(data: dict, template_dir="templates"):
    # Template rendern
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("pdf_template.html")
    rendered_html = template.render(**data)

    # Lokale temp PDF Datei
    filename = f"KI-Readiness-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    local_path = f"/tmp/{filename}"

    # PDF erzeugen
    pdfkit.from_string(rendered_html, local_path)

    # PDF auf S3 hochladen
    s3_key = f"downloads/{filename}"
    try:
        s3_client.upload_file(local_path, bucket_name, s3_key)
        print(f"✅ Hochgeladen: s3://{bucket_name}/{s3_key}")
        return f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{s3_key}"
    except NoCredentialsError:
        print("❌ Keine AWS Credentials gefunden.")
        return None
