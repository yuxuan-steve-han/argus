from abc import ABC, abstractmethod


class DBBackend(ABC):
    @abstractmethod
    def init(self, path: str) -> None:
        """Initialise / connect to the store. Called once at startup."""

    @abstractmethod
    def record(self, camera_id: str, suspicious: bool, changed: bool, reason: str) -> None:
        """Persist one LLM call result."""

    @abstractmethod
    def get_recent(self, window_seconds: int) -> list[dict]:
        """Return all records from the last window_seconds, oldest first.

        Each dict has keys: ts (float), camera_id (str),
        suspicious (bool), changed (bool), reason (str).
        """

    @abstractmethod
    def get_alerts(self, limit: int = 50) -> list[dict]:
        """Return the most recent records where suspicious=true, newest first.

        Each dict has keys: ts (float), camera_id (str),
        changed (bool), reason (str).
        """
