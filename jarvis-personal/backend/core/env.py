from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError as missing:  # an interpreter without requirements.txt (e.g. system Python 3.9)
    raise RuntimeError(
        "The DINCR backend needs Python 3.11 with jarvis-personal/requirements.txt installed "
        f"(missing '{missing.name}'). Scripts: from jarvis-personal/ run python3.11 -m backend.scripts.<name> ..."
    ) from None


def load_backend_env() -> None:
    """Load backend/.env locally without overriding real environment variables."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
