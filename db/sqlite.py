import os
import sqlite3
import threading
import time

from .base import DBBackend


class SQLiteBackend(DBBackend):
    def __init__(self):
        self._lock = threading.Lock()
        self._path = ""

    def init(self, path: str) -> None:
        self._path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         REAL    NOT NULL,
                    camera_id  TEXT    NOT NULL,
                    suspicious INTEGER NOT NULL,
                    changed    INTEGER NOT NULL,
                    reason     TEXT    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON llm_calls (ts)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, check_same_thread=False)

    def record(self, camera_id: str, suspicious: bool, changed: bool, reason: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO llm_calls (ts, camera_id, suspicious, changed, reason) VALUES (?,?,?,?,?)",
                    (time.time(), camera_id, int(suspicious), int(changed), reason),
                )

    def get_recent(self, window_seconds: int) -> list[dict]:
        since = time.time() - window_seconds
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT ts, camera_id, suspicious, changed, reason "
                    "FROM llm_calls WHERE ts >= ? ORDER BY ts ASC",
                    (since,),
                ).fetchall()
        return [
            {"ts": r[0], "camera_id": r[1], "suspicious": bool(r[2]), "changed": bool(r[3]), "reason": r[4]}
            for r in rows
        ]

    def get_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT ts, camera_id, changed, reason "
                    "FROM llm_calls WHERE suspicious = 1 ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {"ts": r[0], "camera_id": r[1], "changed": bool(r[2]), "reason": r[3]}
            for r in rows
        ]
