"""Prevent the two legacy monoliths from growing while they are split gradually."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUDGETS = {
    ROOT / "backend/finance/service.py": 3060,
    ROOT / "frontend/src/pages/Finance.jsx": 1510,
}


def main() -> None:
    failures = []
    for path, maximum in BUDGETS.items():
        lines = len(path.read_text(encoding="utf-8").splitlines())
        print(f"{path.relative_to(ROOT)}: {lines}/{maximum} lines")
        if lines > maximum:
            failures.append(f"{path.relative_to(ROOT)} exceeds {maximum} lines ({lines}).")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
