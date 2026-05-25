# Backend App Package
import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DOTENV_OVERRIDE = os.getenv("DATAFORGE_DOTENV_PATH", "").strip()
_DOTENV_PATH = Path(_DOTENV_OVERRIDE).expanduser() if _DOTENV_OVERRIDE else _BACKEND_DIR / ".env"
load_dotenv(_DOTENV_PATH, override=False)
