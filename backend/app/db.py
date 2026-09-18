import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "ciferki.sqlite3"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                rows INTEGER,
                columns INTEGER,
                sha256 TEXT NOT NULL,
                uploader_id INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                upload_id INTEGER NOT NULL,
                settings TEXT NOT NULL DEFAULT '{}',
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                type TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                summary TEXT NOT NULL DEFAULT '',
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                upload_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'main',
                key_column TEXT NOT NULL DEFAULT '',
                wave_label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        upload_columns = [row["name"] for row in conn.execute("PRAGMA table_info(uploads)")]
        if "structure" not in upload_columns:
            conn.execute("ALTER TABLE uploads ADD COLUMN structure TEXT NOT NULL DEFAULT ''")
        conn.commit()
    finally:
        conn.close()
