"""Fail CI when a server-only credential is committed to a client/public path."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PATHS = (
    ROOT / "frontend",
    ROOT / "android",
)
IGNORED_PARTS = {"node_modules", "dist", "build", ".gradle"}
ASSIGNMENT = re.compile(
    r"(?i)(SUPABASE_SERVICE_ROLE_KEY|SUPABASE_SECRET_KEY|service_role)\s*[:=]\s*['\"]?([^\s,'\"}]+)"
)
PLACEHOLDERS = {"", "<secret>", "your-secret", "change-me", "example", "test"}


def tracked_files() -> set[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT.parent, check=True, capture_output=True, text=True
    )
    return {(ROOT.parent / item).resolve() for item in result.stdout.splitlines() if item}


def main() -> None:
    tracked = tracked_files()
    failures: list[str] = []
    for base in PUBLIC_PATHS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.resolve() not in tracked or IGNORED_PARTS.intersection(path.parts):
                continue
            try:
                value = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for match in ASSIGNMENT.finditer(value):
                secret = match.group(2).strip().lower()
                if secret not in PLACEHOLDERS and not secret.startswith(("${", "process.env", "os.getenv")):
                    failures.append(str(path.relative_to(ROOT)))
                    break
    if failures:
        raise SystemExit("Server-only Supabase secret found in public/client files: " + ", ".join(failures))
    print("No server-only Supabase credentials found in tracked client files.")


if __name__ == "__main__":
    main()
