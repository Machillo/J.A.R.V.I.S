"""DINCR Labs command line: ``python -m labs <command>`` from jarvis-personal/.

The first process (the launcher) never imports the backend. It starts the local
embedded database, then re-runs this module in a child process whose
environment is built from scratch: an allowlist of operating-system variables,
DINCR_ENV=labs and the local Labs database URL. Credentials in the caller's
shell or in backend/.env never reach the Labs process; the child checks the
environment again (labs.guard) before doing anything.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Operating-system variables a Python child needs; nothing application-specific.
PASSTHROUGH = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
               "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
               "PYTHONIOENCODING", "DINCR_LABS_HOME")
CHILD_MARKER = "DINCR_LABS_CHILD"
ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m labs", description="DINCR Labs: isolated, local, synthetic.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check isolation and print the Labs setup (no changes)")
    sub.add_parser("up", help="start the local database and build the Labs schema if needed")
    sub.add_parser("reset", help="drop and rebuild the Labs database (Labs data only)")
    seed = sub.add_parser("seed", help="reset, then load a synthetic dataset")
    seed.add_argument("--scenario", default="normal", choices=("empty", "normal", "heavy", "edge", "broken"))
    seed.add_argument("--seed", type=int, default=7)
    seed.add_argument("--count", type=int, default=5000, help="transactions for the heavy scenario")
    parse = sub.add_parser("parse", help="parser playground on a synthetic email")
    group = parse.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list the email fixtures")
    group.add_argument("--fixture", help="name of a fixture in labs/email_fixtures/bank_emails.json")
    group.add_argument("--file", help="JSON file with synthetic:true, subject, sender, body")
    experiment = sub.add_parser("experiment", help="run an experiment (001, 002, 003)")
    experiment.add_argument("id")
    chaos = sub.add_parser("chaos", help="run experiment 003 (failure simulation)")
    chaos.add_argument("kind", nargs="?", default="all")
    return parser


def _child_env(dsn: str) -> dict[str, str]:
    env = {name: os.environ[name] for name in PASSTHROUGH if name in os.environ}
    env.update({"DINCR_ENV": "labs", "DINCR_LABS_DATABASE_URL": dsn, CHILD_MARKER: "1",
                "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"})
    return env


def launch(argv: list[str]) -> int:
    """Launcher: local database + scrubbed child process. Never imports the backend."""
    _parser().parse_args(argv)  # validate before starting anything
    from labs import db

    server = db.start_server()
    dsn = db.ensure_database(db.admin_uri_for(server))
    completed = subprocess.run([sys.executable, "-m", "labs", *argv], env=_child_env(dsn), cwd=str(ROOT), check=False)
    return completed.returncode


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def child(argv: list[str]) -> int:
    from labs import db, runtime

    args = _parser().parse_args(argv)
    dsn = runtime.activate()
    if args.command == "doctor":
        from labs import netguard

        _print({"environment": "labs", "database": dsn.split("@")[-1], "network": "loopback only" if netguard.installed() else "OPEN",
                "backend_dotenv": "disabled", "status": "isolated"})
        return 0
    if args.command in {"up", "reset"}:
        conn = db._connect(dsn)
        try:
            ready = db.has_marker(conn)
        finally:
            conn.close()
        if args.command == "reset" or not ready:
            db.reset(dsn)
        _print({"database": "ready", "reset": args.command == "reset" or not ready})
        return 0
    if args.command == "seed":
        from labs import seed, synthetic

        db.reset(dsn)
        _print(seed.write(synthetic.build(args.scenario, args.seed, heavy_count=args.count)))
        return 0
    if args.command == "parse":
        from labs import email_lab

        if args.list:
            _print([{"name": c["name"], "description": c["description"]} for c in email_lab.load_fixtures()["cases"]])
            return 0
        if args.fixture:
            message = email_lab.fixture(args.fixture)
        else:
            message = json.loads(Path(args.file).read_text(encoding="utf-8"))
            if message.get("synthetic") is not True:
                print("Refused: the playground only takes files marked \"synthetic\": true (never a real email).")
                return 2
        _print(email_lab.report(message))
        return 0
    if args.command in {"experiment", "chaos"}:
        import importlib

        from labs.experiments import REGISTRY

        key = "003" if args.command == "chaos" else args.id.zfill(3)
        if key not in REGISTRY:
            print(f"Unknown experiment {args.id!r}; available: {', '.join(REGISTRY)}")
            return 2
        _print(importlib.import_module(REGISTRY[key]).run())
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get(CHILD_MARKER) == "1":
        return child(argv)
    return launch(argv)


if __name__ == "__main__":
    sys.exit(main())
