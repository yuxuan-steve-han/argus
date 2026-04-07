"""
Database abstraction layer for LLM call history.

Active backend is selected by DB_BACKEND in .env (default: sqlite).
To add a new backend:
  1. Subclass DBBackend in a new file under db/ and implement the three abstract methods.
  2. Register it in _BACKENDS below.
  3. Set DB_BACKEND=<name> in .env.
"""

from datetime import datetime

from .base import DBBackend
from .sqlite import SQLiteBackend

# ── Backend registry ──────────────────────────────────────────────────────────

_BACKENDS: dict[str, type[DBBackend]] = {
    "sqlite": SQLiteBackend,
}

_backend: DBBackend | None = None


def _get() -> DBBackend:
    if _backend is None:
        raise RuntimeError("db.init() has not been called")
    return _backend


# ── Public API ────────────────────────────────────────────────────────────────

def init(path: str) -> None:
    global _backend
    import config as _config
    name = _config.DB_BACKEND.lower()
    cls = _BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"Unknown DB_BACKEND {name!r}. Available: {list(_BACKENDS)}")
    _backend = cls()
    _backend.init(path)


def record(camera_id: str, suspicious: bool, changed: bool, reason: str) -> None:
    _get().record(camera_id, suspicious, changed, reason)


def get_recent(window_seconds: int) -> list[dict]:
    return _get().get_recent(window_seconds)


def get_alerts(limit: int = 50) -> list[dict]:
    return _get().get_alerts(limit)


def format_history(records: list[dict]) -> str:
    """Pure formatting — not backend-specific."""
    if not records:
        return "No recent activity."
    lines = []
    for r in records:
        t = datetime.fromtimestamp(r["ts"]).strftime("%H:%M:%S")
        status = "SUSPICIOUS" if r["suspicious"] else "clear"
        lines.append(f"  {t} [{r['camera_id']}] {status}: {r['reason']}")
    return "\n".join(lines)
