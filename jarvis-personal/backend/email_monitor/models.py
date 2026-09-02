from __future__ import annotations

from pydantic import BaseModel


class EmailTextScanRequest(BaseModel):
    subject: str = ""
    sender: str = ""
    body: str
    received_at: str | None = None
    auto_commit: bool = False


class EmailCandidateDecisionRequest(BaseModel):
    candidate_id: int
    decision: str  # confirm | reject


class EmailCandidateClassifyRequest(BaseModel):
    candidate_id: int
    description: str
    transaction_type: str
    category: str
    remember_rule: bool = True
    auto_commit_future: bool = True



class EmailCandidateBulkDecisionRequest(BaseModel):
    candidate_ids: list[int]
    decision: str  # confirm | reject


class EmailStatementReconcileRequest(BaseModel):
    statement_id: int
