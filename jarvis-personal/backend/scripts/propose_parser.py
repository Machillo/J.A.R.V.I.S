"""Internal CLI: sanitize unknown bank email samples and ask for a PENDING parser proposal.

Two explicit steps (from jarvis-personal/, samples kept OUTSIDE the repository):

    python -m backend.scripts.propose_parser C:/samples/bn1.txt C:/samples/bn2.txt
        -> writes parser_proposals/bn1.sanitized.txt ... and prints them. Nothing is sent.

    # read every *.sanitized.txt, then:
    python -m backend.scripts.propose_parser --send parser_proposals/bn1.sanitized.txt parser_proposals/bn2.sanitized.txt

--send accepts only *.sanitized.txt files that sanitizing again leaves unchanged, and
needs PARSER_DISCOVERY_ENABLED=true and OPENAI_API_KEY. The result is a
PENDING_HUMAN_REVIEW JSON file that the app never loads: a human turns an approved
proposal into a deterministic parser plus synthetic tests in a normal reviewed PR.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.parser_discovery.proposal import propose
from backend.parser_discovery.sanitize import SANITIZED_SUFFIX, is_sanitized, sanitize_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("samples", nargs="+", type=Path, help="raw samples, or *.sanitized.txt files with --send")
    parser.add_argument("--send", action="store_true", help="send reviewed *.sanitized.txt files to the provider")
    parser.add_argument("--out", type=Path, default=Path("parser_proposals"), help="folder for sanitized samples and proposals")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.send:
        for path in args.samples:
            sanitized = sanitize_sample(path.read_text(encoding="utf-8"))
            target = args.out / f"{path.stem}{SANITIZED_SUFFIX}"
            target.write_text(sanitized, encoding="utf-8")
            print(f"=== {target} ===\n{sanitized}\n")
        print("Nothing was sent. Read the files above, then re-run with --send and those *.sanitized.txt files.")
        return 0

    samples = []
    for path in args.samples:
        text = path.read_text(encoding="utf-8")
        if not path.name.endswith(SANITIZED_SUFFIX) or not is_sanitized(text):
            print(f"Refusing {path}: only reviewed {SANITIZED_SUFFIX} files from the dry run can be sent.", file=sys.stderr)
            return 1
        samples.append(text)

    try:
        proposal = propose(samples)
    except (RuntimeError, ValueError) as exc:
        print(f"No proposal: {exc}", file=sys.stderr)
        return 1

    target = args.out / f"{proposal['bank']}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PENDING proposal written to {target}. It is not active; review it before writing any parser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
