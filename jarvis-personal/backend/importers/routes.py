import shutil
import tempfile

from fastapi import APIRouter, File, UploadFile

from backend.importers.bac_pdf import parse_bac_credit_card_pdf


router = APIRouter(prefix="/imports", tags=["Imports"])


@router.post("/bac-pdf/preview")
def preview_bac_pdf(file: UploadFile = File(...)):
    # The client filename never becomes a path: a server-generated temporary file,
    # removed after parsing (no statement is kept on disk).
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as temp:
        shutil.copyfileobj(file.file, temp)
        temp.flush()
        return parse_bac_credit_card_pdf(temp.name)
