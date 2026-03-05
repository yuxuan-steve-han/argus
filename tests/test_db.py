import sqlite3
import time

import pytest

import db
from db.sqlite import SQLiteBackend


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_backend(tmp_path) -> SQLiteBackend:
    b = SQLiteBackend()
    b.init(str(tmp_path / "test.db"))
    return b


def insert_at(db_path: str, ts: float, camera_id: str, suspicious: bool, changed: bool, reason: str):
    """Insert a record with an explicit timestamp (bypasses time.time())."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO llm_calls (ts, camera_id, suspicious, changed, reason) VALUES (?,?,?,?,?)",
            (ts, camera_id, int(suspicious), int(changed), reason),
        )


# ── SQLiteBackend ──────────────────────────────────────────────────────────────

class TestSQLiteBackend:
    def test_init_creates_table(self, tmp_path):
        b = make_backend(tmp_path)
        with sqlite3.connect(str(tmp_path / "test.db")) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert ("llm_calls",) in tables

    def test_record_and_retrieve(self, tmp_path):
        b = make_backend(tmp_path)
        b.record("cam0", True, True, "person lurking")
        rows = b.get_recent(60)
        assert len(rows) == 1
        r = rows[0]
        assert r["camera_id"] == "cam0"
        assert r["suspicious"] is True
        assert r["changed"] is True
        assert r["reason"] == "person lurking"
        assert isinstance(r["ts"], float)

    def test_get_recent_excludes_old_records(self, tmp_path):
        b = make_backend(tmp_path)
        db_path = str(tmp_path / "test.db")
        insert_at(db_path, time.time() - 400, "cam0", False, False, "old event")
        rows = b.get_recent(300)
        assert rows == []

    def test_get_recent_includes_recent_records(self, tmp_path):
        b = make_backend(tmp_path)
        db_path = str(tmp_path / "test.db")
        insert_at(db_path, time.time() - 60, "cam0", True, True, "recent event")
        rows = b.get_recent(300)
        assert len(rows) == 1
        assert rows[0]["reason"] == "recent event"

    def test_records_returned_oldest_first(self, tmp_path):
        b = make_backend(tmp_path)
        b.record("cam0", False, False, "first")
        b.record("cam1", True, True, "second")
        rows = b.get_recent(60)
        assert len(rows) == 2
        assert rows[0]["reason"] == "first"
        assert rows[1]["reason"] == "second"

    def test_multiple_cameras(self, tmp_path):
        b = make_backend(tmp_path)
        b.record("cam0", False, False, "clear")
        b.record("cam1", True, True, "intruder")
        b.record("cam2", False, False, "clear")
        rows = b.get_recent(60)
        assert len(rows) == 3
        assert {r["camera_id"] for r in rows} == {"cam0", "cam1", "cam2"}

    def test_boolean_fields_are_bool(self, tmp_path):
        b = make_backend(tmp_path)
        b.record("cam0", True, False, "test")
        rows = b.get_recent(60)
        assert rows[0]["suspicious"] is True
        assert rows[0]["changed"] is False

    def test_thread_safety(self, tmp_path):
        import threading
        b = make_backend(tmp_path)
        errors = []

        def write_records():
            try:
                for i in range(20):
                    b.record("cam0", False, False, f"event {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_records) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        rows = b.get_recent(60)
        assert len(rows) == 100  # 5 threads × 20 records


# ── format_history ─────────────────────────────────────────────────────────────

class TestFormatHistory:
    def test_empty_list(self):
        assert db.format_history([]) == "No recent activity."

    def test_suspicious_record(self):
        records = [{"ts": 1700000000.0, "camera_id": "cam0", "suspicious": True, "changed": True, "reason": "person lurking"}]
        text = db.format_history(records)
        assert "cam0" in text
        assert "SUSPICIOUS" in text
        assert "person lurking" in text

    def test_clear_record(self):
        records = [{"ts": 1700000000.0, "camera_id": "cam1", "suspicious": False, "changed": False, "reason": "all clear"}]
        text = db.format_history(records)
        assert "cam1" in text
        assert "clear" in text
        assert "all clear" in text

    def test_multiple_records(self):
        records = [
            {"ts": 1700000000.0, "camera_id": "cam0", "suspicious": True, "changed": True, "reason": "intruder"},
            {"ts": 1700000060.0, "camera_id": "cam1", "suspicious": False, "changed": False, "reason": "clear"},
        ]
        text = db.format_history(records)
        assert "cam0" in text
        assert "cam1" in text
        lines = text.strip().splitlines()
        assert len(lines) == 2
