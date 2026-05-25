# Backend App Package
from pathlib import Path
from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env", override=False)
