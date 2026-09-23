import os
from pathlib import Path

from dotenv import load_dotenv


LEGACY_ENV_PREFIX = "FINVA_"
ENV_PREFIX = "DINCR_"


def alias_legacy_brand_env() -> None:
    """Expose legacy FINVA_* variables as DINCR_* until every host is renamed.

    The code only reads DINCR_*. An explicit DINCR_* value always wins, so the
    old names can be deleted from Render/Vercel once the new ones exist.
    """
    for name, value in list(os.environ.items()):
        if name.startswith(LEGACY_ENV_PREFIX):
            os.environ.setdefault(ENV_PREFIX + name[len(LEGACY_ENV_PREFIX):], value)


def load_backend_env() -> None:
    """Load backend/.env locally without overriding real environment variables."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    alias_legacy_brand_env()
