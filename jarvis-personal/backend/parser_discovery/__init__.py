"""Internal, human-gated discovery of parsers for unknown bank email formats.

AI proposes, deterministic DINCR executes, humans approve:
- samples are sanitized locally before anything leaves the machine;
- the model returns a declarative proposal (regexes + keywords), never code;
- every proposal is stored as PENDING_HUMAN_REVIEW and nothing here is
  imported by the live ingestion pipeline. A human turns an approved proposal
  into a deterministic parser with tests, through a normal reviewed PR.
"""

PENDING = "PENDING_HUMAN_REVIEW"
