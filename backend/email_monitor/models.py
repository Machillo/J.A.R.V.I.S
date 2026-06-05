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
