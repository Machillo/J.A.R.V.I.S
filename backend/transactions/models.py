from pydantic import BaseModel


class TransactionRequest(BaseModel):
    transaction_date: str
    description: str
    amount: float
    transaction_type: str
    category: str
    account: str = ""
    source: str = "manual"
    notes: str = ""
    original_amount: float | None = None
    original_currency: str | None = None
    exchange_rate: float | None = None


class TransactionUpdateRequest(BaseModel):
    transaction_date: str
    description: str
    amount: float
    transaction_type: str
    category: str
    account: str = ""
    source: str = "manual"
    notes: str = ""
    original_amount: float | None = None
    original_currency: str | None = None
    exchange_rate: float | None = None


class TransactionParseRequest(BaseModel):
    text: str


class TransactionBulkImportRequest(BaseModel):
    transactions: list[TransactionRequest]