"""Internal CLI: sanitize unknown bank email samples and ask for a PENDING parser proposal.

Usage (from jarvis-personal/):

    python -m backend.scripts.propose_parser sample1.txt sample2.txt            # dry run: prints sanitized samples
    python -m backend.scripts.propose_parser sample1.txt --send --out parser_proposals

--send needs PARSER_DISCOVERY_ENABLED=true and OPENAI_API_KEY. Only sanitized text
leaves the machine. The result is a PENDING_HUMAN_REVIEW JSON file: it is never
loaded by the app. A human turns an approved proposal into a deterministic parser
plus synthetic tests in a normal reviewed PR.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.parser_discovery.proposal import propose
from backend.parser_discovery.sanitize import residual_risks, sanitize_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("samples", nargs="+", type=Path, help="plain-text email samples (UTF-8)")
    parser.add_argument("--send", action="store_true", help="send the sanitized samples to the provider")
    parser.add_argument("--out", type=Path, default=Path("parser_proposals"), help="folder for the PENDING proposal")
    args = parser.parse_args(argv)

    samples = [sanitize_sample(path.read_text(encoding="utf-8")) for path in args.samples]
    for path, sample in zip(args.samples, samples):
        risks = residual_risks(sample)
        print(f"=== {path.name} (sanitized){' — REVIEW: ' + ', '.join(risks) if risks else ''} ===\n{sample}\n")

    if not args.send:
        print("Dry run: nothing was sent. Review the text above, then re-run with --send.")
        return 0

    try:
        proposal = propose(samples)
    except (RuntimeError, ValueError) as exc:
        print(f"No proposal: {exc}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{proposal['bank']}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PENDING proposal written to {target}. It is not active; review it before writing any parser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
