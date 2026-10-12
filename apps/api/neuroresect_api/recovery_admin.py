"""Inspect a restored Compose database and finalize its interrupted jobs offline."""

import argparse
import hashlib
import json
import re

from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url

from .config import Settings
from .database import Base, Database, JobRecord
from .migrations import status
from .repository import utcnow


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ValueError("Use a lowercase database identifier of at most 63 characters")
    return value


def inspect_recovery(database: Database, finalize: bool = False) -> dict:
    schema = status(database.engine)
    if schema["current"] != [schema["head"]] or not schema["schema_matches_models"]:
        raise ValueError(
            "Recovery requires a database at the installed schema revision without drift"
        )
    with database.engine.begin() as connection:
        counts = {
            name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in Base.metadata.tables.items()
        }
        interrupted = 0
        if finalize:
            interrupted = connection.execute(
                update(JobRecord)
                .where(JobRecord.status.in_(["QUEUED", "RUNNING"]))
                .values(
                    status="FAILED",
                    stage="RESTORED_INTERRUPTED",
                    updated_at=utcnow(),
                    error={
                        "code": "BACKUP_INTERRUPTED",
                        "message": "Restored from a snapshot. Submit a new job with a new idempotency key.",
                        "details": {},
                    },
                )
            ).rowcount
        hashes = {}
        for name, table in Base.metadata.tables.items():
            digest = hashlib.sha256()
            rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            for row in rows:
                digest.update(
                    json.dumps(dict(row), sort_keys=True, default=str, allow_nan=False).encode()
                )
                digest.update(b"\n")
            hashes[name] = digest.hexdigest()
    return {
        "table_sha256": hashes,
        "schema_revision": schema["head"],
        "row_counts": counts,
        "interrupted_jobs": interrupted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-name", required=True, type=identifier)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    url = make_url(Settings.from_env().database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("Compose recovery inspection requires PostgreSQL")
    database = Database(url.set(database=args.database_name).render_as_string(hide_password=False))
    try:
        result = inspect_recovery(database, args.finalize)
    finally:
        database.close()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
