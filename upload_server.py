
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import os

app = FastAPI()

@app.get("/upload-template", response_class=HTMLResponse)
async def upload_form():
    with open("placid-upload.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post("/upload-template")
async def handle_template_upload(file: UploadFile = File(...)):
    file_location = f"templates/{file.filename}"
    os.makedirs(os.path.dirname(file_location), exist_ok=True)
    with open(file_location, "wb") as f:
        f.write(await file.read())
    return {"info": f"file '{file.filename}' saved at '{file_location}'"}
