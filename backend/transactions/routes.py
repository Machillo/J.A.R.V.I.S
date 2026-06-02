from fastapi import APIRouter
from backend.transactions.parser import parse_transaction_text, parse_and_save_transaction_text
from backend.transactions.analyzer import get_transaction_analysis


from backend.transactions.models import (
    TransactionRequest,
    TransactionParseRequest,
    TransactionBulkImportRequest,
    TransactionUpdateRequest,
)

from backend.transactions.service import (
    create_transaction,
    get_transactions,
    get_transaction,
    delete_transaction,
    bulk_create_transactions,
    update_transaction,
)


router = APIRouter(prefix="/transactions", tags=["Transactions"])


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


@router.get("/")
def transactions():
    return get_transactions()


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

@router.post("/parse")
def parse_transaction(request: TransactionParseRequest):
    parsed = parse_transaction_text(request.text)

    return parsed

@router.post("/parse-and-save")
def parse_and_save_transaction(request: TransactionParseRequest):
    return parse_and_save_transaction_text(request.text)

@router.get("/analysis/summary")
def transaction_analysis():
    return get_transaction_analysis()

@router.post("/bulk-import")
def bulk_import_transactions(request: TransactionBulkImportRequest):
    transactions = [
        transaction.model_dump()
        for transaction in request.transactions
    ]

    return bulk_create_transactions(transactions)