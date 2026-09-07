"""SQLite persistence for agent tasks and session activity."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import AgentState

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "workbench.sqlite3"
_lock = threading.RLock()


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


DEFAULT_TITLE = "New chat"


def initialize() -> None:
    with _lock, _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New chat',
                updated_at REAL NOT NULL
            )
            """
        )
        # Migration for DBs created before `title` existed.
        existing_cols = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}
        if "title" not in existing_cols:
            connection.execute(f"ALTER TABLE sessions ADD COLUMN title TEXT NOT NULL DEFAULT '{DEFAULT_TITLE}'")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id)")


def save_state(state: AgentState) -> None:
    initialize()
    payload = json.dumps(state.dict(), ensure_ascii=False)
    timestamp = time.time()
    with _lock, _connection() as connection:
        connection.execute(
            """
            INSERT INTO tasks(task_id, session_id, status, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                session_id=excluded.session_id,
                status=excluded.status,
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (state.task_id, state.session_id, state.status, payload, timestamp),
        )
        # Bumps updated_at for sorting but deliberately leaves `title`
        # alone on conflict — renaming (e.g. autoname on first message) is
        # a separate, explicit call via rename_session().
        connection.execute(
            f"""
            INSERT INTO sessions(session_id, title, updated_at) VALUES (?, '{DEFAULT_TITLE}', ?)
            ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (state.session_id, timestamp),
        )


def create_session(session_id: str, title: str = DEFAULT_TITLE) -> None:
    """Registers a chat immediately, even before it has any messages, so a
    freshly-created "New chat" survives a page refresh instead of only
    existing in the frontend's React state until the first task lands."""
    initialize()
    with _lock, _connection() as connection:
        connection.execute(
            """
            INSERT INTO sessions(session_id, title, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO NOTHING
            """,
            (session_id, title, time.time()),
        )


def rename_session(session_id: str, title: str) -> None:
    initialize()
    with _lock, _connection() as connection:
        connection.execute(
            """
            INSERT INTO sessions(session_id, title, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at
            """,
            (session_id, title, time.time()),
        )


def get_session_title(session_id: str) -> str | None:
    initialize()
    with _lock, _connection() as connection:
        row = connection.execute(
            "SELECT title FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return row["title"] if row else None


def delete_session(session_id: str) -> None:
    """Removes a chat and every task that belongs to it."""
    initialize()
    with _lock, _connection() as connection:
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))


def load_states() -> list[AgentState]:
    initialize()
    with _lock, _connection() as connection:
        rows = connection.execute("SELECT state_json FROM tasks ORDER BY updated_at").fetchall()
    return [AgentState.parse_raw(row["state_json"]) for row in rows]


def list_sessions() -> list[dict]:
    initialize()
    with _lock, _connection() as connection:
        rows = connection.execute(
            "SELECT session_id, title, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"id": row["session_id"], "title": row["title"] or DEFAULT_TITLE, "updated_at": row["updated_at"]}
        for row in rows
    ]