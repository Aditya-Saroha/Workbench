from contextvars import ContextVar
import os
import re
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
_current_session: ContextVar[str] = ContextVar("rag_session", default="default")


def normalize_session_id(session_id: str | None) -> str:
    value = (session_id or "default").strip()
    value = re.sub(r"[^a-zA-Z0-9_-]", "-", value)[:80]
    return value or "default"


def session_root(session_id: str | None = None) -> str:
    return os.path.join(SESSIONS_DIR, normalize_session_id(session_id or _current_session.get()))


def documents_dir(session_id: str | None = None) -> str:
    return os.path.join(session_root(session_id), "documents")


def data_dir(session_id: str | None = None) -> str:
    return os.path.join(session_root(session_id), "data")


@contextmanager
def session_scope(session_id: str | None):
    token = _current_session.set(normalize_session_id(session_id))
    os.makedirs(documents_dir(), exist_ok=True)
    os.makedirs(data_dir(), exist_ok=True)
    try:
        yield
    finally:
        _current_session.reset(token)
