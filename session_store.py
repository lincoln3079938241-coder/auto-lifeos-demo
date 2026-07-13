from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from database.seed import seed_database
from database.session import bind_database, dispose_database, get_session, initialize_database


@dataclass
class SessionWorkspace:
    """Owns one temporary SQLite database for one Streamlit browser session."""

    session_id: str = field(default_factory=lambda: str(uuid4()))
    _temporary_directory: TemporaryDirectory[str] = field(
        default_factory=lambda: TemporaryDirectory(prefix="auto-lifeos-demo-", ignore_cleanup_errors=True)
    )

    @property
    def database_path(self) -> Path:
        return Path(self._temporary_directory.name) / "session.sqlite3"

    def activate(self) -> None:
        bind_database(self.database_path)
        initialize_database()
        with get_session() as session:
            seed_database(session)

    def reset(self) -> None:
        dispose_database(self.database_path)
        self.database_path.unlink(missing_ok=True)
        self.activate()

    def close(self) -> None:
        dispose_database(self.database_path)
        self._temporary_directory.cleanup()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
