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
