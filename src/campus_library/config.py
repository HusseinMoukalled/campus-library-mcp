"""Configuration never prints or forwards API keys to the MCP subprocess."""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_settings() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def database_path() -> Path:
    file_value = dotenv_values(PROJECT_ROOT / ".env").get("LIBRARY_DB_PATH")
    path = Path(os.getenv("LIBRARY_DB_PATH") or file_value or "runtime/library.sqlite3")
    return path if path.is_absolute() else PROJECT_ROOT / path
