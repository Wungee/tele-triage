"""Runtime configuration, read from environment variables (and an optional .env file at the repo root)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", str(ROOT / "artifacts")))
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(ROOT / "frontend" / "dist")))

# Optional: Gemini writes a plain-English summary of the evidence. Without a key we fall back
# to a deterministic template, so the demo never depends on a network call.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Optional: postgres://... pointing at TimescaleDB (Tiger Data). Empty = local SQLite file.
DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(ROOT / "data" / "reviews.db")))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "20"))
