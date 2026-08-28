from fastapi import APIRouter

from backend.transactions.models import TransactionRequest, TransactionUpdateRequest
from backend.transactions.service import create_transaction, delete_transaction, get_transactions, update_transaction


router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("")
def transactions():
    return get_transactions()


@router.post("")
def add_transaction(request: TransactionRequest):
    return create_transaction(**request.model_dump())


@router.put("/{transaction_id}")
def edit_transaction(transaction_id: int, request: TransactionUpdateRequest):
    return update_transaction(transaction_id, **request.model_dump())


@router.delete("/{transaction_id}")
def remove_transaction(transaction_id: int):
    return delete_transaction(transaction_id)
