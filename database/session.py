from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from threading import RLock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base


_current_database_url: ContextVar[str | None] = ContextVar("current_database_url", default=None)
_engines: dict[str, Engine] = {}
_factories: dict[str, sessionmaker[Session]] = {}
_lock = RLock()


def database_url_for(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def bind_database(path: Path) -> str:
    """Bind all repository calls in the current context to one session database."""
    url = database_url_for(path)
    _current_database_url.set(url)
    with _lock:
        if url not in _engines:
            engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
            _engines[url] = engine
            _factories[url] = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    return url


def _bound_url() -> str:
    url = _current_database_url.get()
    if not url:
        raise RuntimeError("Session database is not bound")
    return url


def get_engine() -> Engine:
    url = _bound_url()
    return _engines[url]


def get_session() -> Session:
    url = _bound_url()
    return _factories[url]()


def initialize_database() -> None:
    Base.metadata.create_all(get_engine())


def dispose_database(path: Path) -> None:
    url = database_url_for(path)
    with _lock:
        engine = _engines.pop(url, None)
        _factories.pop(url, None)
    if engine is not None:
        engine.dispose()

