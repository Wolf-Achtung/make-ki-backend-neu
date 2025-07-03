import os
from weasyprint import HTML

def create_pdf(content, filename):
    output_dir = "downloads"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    HTML(string=content).write_pdf(output_path)
    return output_path
