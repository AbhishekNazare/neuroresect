"""Serialized schema upgrades and explicit adoption of verified legacy databases."""

import argparse
import json
import os
from pathlib import Path
from threading import RLock

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from .baseline_schema import Base as Baseline
from .database import Base, Database

BASELINE = "0001_research_records"
_lock = RLock()  # Alembic's module-level environment is not thread-local.


def configuration(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migration_scripts"))
    config.attributes["connection"] = connection
    return config


def head_revision() -> str:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migration_scripts"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def differences(connection: Connection, metadata) -> list:
    return compare_metadata(
        MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        ),
        metadata,
    )


def lock_database(connection: Connection) -> None:
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    elif connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(734624501)"))
    else:
        raise ValueError("Only SQLite and PostgreSQL migrations are supported")


def status(engine: Engine) -> dict:
    with engine.connect() as connection:
        tables = inspect(connection).get_table_names()
        heads = MigrationContext.configure(connection).get_current_heads()
        return {
            "current": list(heads),
            "head": head_revision(),
            "empty": not tables,
            "legacy": bool(tables) and not heads,
            "schema_matches_models": bool(tables) and not differences(connection, Base.metadata),
        }


def upgrade(engine: Engine, *, allow_legacy: bool = False) -> dict:
    with _lock, engine.begin() as connection:
        lock_database(connection)
        tables = inspect(connection).get_table_names()
        heads = MigrationContext.configure(connection).get_current_heads()
        config = configuration(connection)
        if tables and not heads:
            if not allow_legacy:
                raise RuntimeError(
                    "Unversioned database. Back up first, then run python -m neuroresect_api.migrations upgrade --adopt-legacy"
                )
            if differences(connection, Baseline.metadata):
                raise RuntimeError(
                    "Legacy schema differs from the frozen baseline; adoption refused"
                )
            command.stamp(config, BASELINE)
        command.upgrade(config, "head")
        if differences(connection, Base.metadata):
            raise RuntimeError("Schema differs from the installed models after migration")
    return status(engine)


def initialize(engine: Engine) -> None:
    # Fresh installations bootstrap automatically. Existing installations require explicit upgrades.
    with _lock, engine.begin() as connection:
        lock_database(connection)
        tables = inspect(connection).get_table_names()
        if not tables:
            command.upgrade(configuration(connection), "head")
        heads = MigrationContext.configure(connection).get_current_heads()
        if heads != (head_revision(),):
            raise RuntimeError(
                "Database schema needs an explicit upgrade. Run python -m neuroresect_api.migrations status; back up before upgrading"
            )
        if differences(connection, Base.metadata):
            raise RuntimeError("Database schema drift detected; refusing startup")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "upgrade"])
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///./data/neuroresect.db")
    )
    parser.add_argument(
        "--adopt-legacy",
        action="store_true",
        help="Adopt only an exact frozen legacy schema after backup",
    )
    args = parser.parse_args()
    database = Database(args.database_url)
    try:
        result = (
            status(database.engine)
            if args.action == "status"
            else upgrade(database.engine, allow_legacy=args.adopt_legacy)
        )
    finally:
        database.close()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
