import sys

# The backend, its scripts and its tests run on Python 3.11 (runtime.txt); its
# pinned dependencies (e.g. python-dotenv 1.2) do not install on older versions.
if sys.version_info < (3, 11):
    raise RuntimeError(
        f"The DINCR backend needs Python 3.11 (found {sys.version.split()[0]}). "
        "Scripts: from jarvis-personal/ run python3.11 -m backend.scripts.<name> ..."
    )

from backend.core.env import load_backend_env  # noqa: E402

load_backend_env()
