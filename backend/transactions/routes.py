from fastapi import APIRouter, File, Form, UploadFile

from backend.transactions.analyzer import get_transaction_analysis
from backend.transactions.finance_input import (
    commit_finance_preview,
    extract_pdf_upload_text,
    parse_finance_text,
)
from backend.transactions.models import (
    FinanceInputCommitRequest,
    FinanceInputPreviewRequest,
    TransactionBulkImportRequest,
    TransactionParseRequest,
    TransactionRequest,
    TransactionUpdateRequest,
)
from backend.transactions.parser import parse_and_save_transaction_text, parse_transaction_text
from backend.transactions.service import (
    bulk_create_transactions,
    create_transaction,
    delete_transaction,
    get_transaction,
    get_transactions,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("/")
def transactions():
    return get_transactions()


@router.post("/")
def add_transaction(request: TransactionRequest):
    return create_transaction(
        transaction_date=request.transaction_date,
        description=request.description,
        amount=request.amount,
        transaction_type=request.transaction_type,
        category=request.category,
        account=request.account,
        source=request.source,
        notes=request.notes,
        original_amount=request.original_amount,
        original_currency=request.original_currency,
        exchange_rate=request.exchange_rate,
    )


@router.get("/analysis/summary")
def transaction_analysis():
    return get_transaction_analysis()


@router.post("/bulk-import")
def bulk_import_transactions(request: TransactionBulkImportRequest):
    return bulk_create_transactions([transaction.model_dump() for transaction in request.transactions])


@router.post("/parse")
def parse_transaction(request: TransactionParseRequest):
    return parse_transaction_text(request.text)


@router.post("/parse-and-save")
def parse_and_save_transaction(request: TransactionParseRequest):
    return parse_and_save_transaction_text(request.text)


@router.post("/finance-input/preview")
def preview_finance_input(request: FinanceInputPreviewRequest):
    return parse_finance_text(
        text=request.text,
        default_year_month=request.default_year_month,
        default_exchange_rate=request.exchange_rate,
    )


@router.post("/finance-input/commit")
def commit_finance_input(request: FinanceInputCommitRequest):
    return commit_finance_preview([transaction.model_dump() for transaction in request.transactions])


@router.post("/finance-input/pdf-preview")
def preview_finance_pdf(
    file: UploadFile = File(...),
    default_year_month: str | None = Form(default=None),
    exchange_rate: float = Form(default=495.0),
):
    text = extract_pdf_upload_text(file)
    result = parse_finance_text(text, default_year_month, exchange_rate)
    result["source_file"] = file.filename
    return result


@router.get("/{transaction_id}")
def transaction(transaction_id: int):
    return get_transaction(transaction_id)


@router.put("/{transaction_id}")
def edit_transaction(transaction_id: int, request: TransactionUpdateRequest):
    return update_transaction(
        transaction_id=transaction_id,
        transaction_date=request.transaction_date,
        description=request.description,
        amount=request.amount,
        transaction_type=request.transaction_type,
        category=request.category,
        account=request.account,
        source=request.source,
        notes=request.notes,
        original_amount=request.original_amount,
        original_currency=request.original_currency,
        exchange_rate=request.exchange_rate,
    )


@router.delete("/{transaction_id}")
def remove_transaction(transaction_id: int):
    return delete_transaction(transaction_id)
