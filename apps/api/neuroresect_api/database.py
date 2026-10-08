"""Small relational persistence layer compatible with SQLite and PostgreSQL."""

from pathlib import Path
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class ScenarioRecord(Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(96), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ImportRecord(Base):
    __tablename__ = "imported_connectomes"
    patient_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    atlas_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    patient: Mapped[dict[str, Any]] = mapped_column(JSON)
    connectome: Mapped[dict[str, Any]] = mapped_column(JSON)


class ResultRecord(Base):
    __tablename__ = "scenario_results"
    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ExperimentRecord(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class JobRecord(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    executor: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    progress: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True))
    idempotency_scope: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64))


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        options: dict[str, Any] = {"pool_pre_ping": True}
        if parsed.get_backend_name() == "sqlite":
            options["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if parsed.database in {None, "", ":memory:"}:
                options["poolclass"] = StaticPool
            else:
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, **options)
        if parsed.get_backend_name() == "sqlite":

            @event.listens_for(self.engine, "connect")
            def sqlite_pragmas(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()
