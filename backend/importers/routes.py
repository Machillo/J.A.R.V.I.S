import os
import shutil
from fastapi import APIRouter, UploadFile, File

from backend.importers.bac_pdf import parse_bac_credit_card_pdf


router = APIRouter(prefix="/imports", tags=["Imports"])


@router.post("/bac-pdf/preview")
def preview_bac_pdf(file: UploadFile = File(...)):
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = parse_bac_credit_card_pdf(file_path)

    return result