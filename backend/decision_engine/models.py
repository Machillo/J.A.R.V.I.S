from pydantic import BaseModel


class ExtraMoneyDecisionRequest(BaseModel):
    amount: float
    source: str = "extra_money"
    description: str = ""