from pydantic import BaseModel, Field


class TransactionRequest(BaseModel):
    transaction_date: str
    description: str
    amount: float = Field(gt=0)
    transaction_type: str
    category: str = "general"
    notes: str = ""


class TransactionUpdateRequest(TransactionRequest):
    pass
