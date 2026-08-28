from pathlib import Path

from dotenv import load_dotenv


def load_backend_env() -> None:
    """Load backend/.env for local development without overriding real env vars."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
