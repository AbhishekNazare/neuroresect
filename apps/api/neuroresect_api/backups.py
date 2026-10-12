"""Verified SQLite snapshots and restore-to-new-path operations for local research."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from . import __version__
from .database import Base

FORMAT = "neuroresect-sqlite-backup-v1"
SCHEMA_SQL = "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"


def fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sqlite_path(url: str) -> Path:
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "sqlite"
        or not parsed.database
        or parsed.database == ":memory:"
        or parsed.query
    ):
        raise ValueError(
            "Use a file-backed SQLite URL without query options; PostgreSQL and memory databases are not supported"
        )
    return Path(parsed.database).absolute()


def readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True, timeout=5)


def normalize_schema(rows) -> list[list[str]]:
    return [[kind, name, " ".join(sql.split())] for kind, name, sql in rows]


def inspect_database(connection: sqlite3.Connection) -> dict:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("SQLite foreign-key check failed")
    schema = normalize_schema(connection.execute(SCHEMA_SQL).fetchall())
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as expected:
            supported = normalize_schema(expected.exec_driver_sql(SCHEMA_SQL).fetchall())
    finally:
        engine.dispose()
    if schema != supported:
        raise ValueError(
            "Database schema differs from this application; use the matching application revision"
        )
    return {
        "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
        "row_counts": {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in sorted(Base.metadata.tables)
        },
        "job_status_counts": dict(
            connection.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        ),
    }


def flush(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def backup(database_url: str, destination: Path, timeout: float = 60) -> dict:
    source = sqlite_path(database_url)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be positive")
    # Opening read-only fails for absent sources rather than creating an empty database.
    with closing(readonly(source)) as origin:
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            snapshot = destination / "database.sqlite3"
            snapshot.touch(mode=0o600, exist_ok=False)
            deadline = time.monotonic() + timeout

            def progress(_status, _remaining, _total):
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        "Backup deadline exceeded; try again when writes are quieter"
                    )

            with closing(sqlite3.connect(snapshot)) as target:
                origin.backup(target, pages=256, progress=progress, sleep=0.05)
                target.execute("PRAGMA journal_mode=DELETE")
                details = inspect_database(target)
            flush(snapshot)
            manifest = {
                "format": FORMAT,
                "application_version": __version__,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "database_sha256": fingerprint(snapshot),
                "database_bytes": snapshot.stat().st_size,
                **details,
                "scope": "SQLite application records only; excludes source datasets, external artifacts and broker queues",
            }
            manifest_path = destination / "manifest.json"
            with manifest_path.open("x") as stream:
                os.chmod(manifest_path, 0o600)
                json.dump(manifest, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(destination)
            sync_directory(destination.parent)
            return manifest
        except BaseException:
            shutil.rmtree(destination)
            raise


def verify(bundle: Path) -> dict:
    manifest = json.loads((bundle / "manifest.json").read_text())
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ValueError("Unsupported backup format")
    snapshot = bundle / "database.sqlite3"
    if (
        snapshot.stat().st_size != manifest["database_bytes"]
        or fingerprint(snapshot) != manifest["database_sha256"]
    ):
        raise ValueError("Backup checksum or size mismatch")
    if any(os.path.lexists(str(snapshot) + suffix) for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Backup must be a standalone snapshot without SQLite sidecars")
    with closing(readonly(snapshot)) as connection:
        details = inspect_database(connection)
    if any(manifest[key] != value for key, value in details.items()):
        raise ValueError("Backup inventory differs from its manifest")
    return manifest


def restore(bundle: Path, destination: Path) -> dict:
    # Always restore to a new path. No force option can replace a live research database.
    destination = destination.absolute()
    if os.path.lexists(destination) or any(
        os.path.lexists(str(destination) + suffix) for suffix in ("-wal", "-shm", "-journal")
    ):
        raise FileExistsError("Restore requires a new database path without SQLite sidecars")
    manifest = verify(bundle)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".neuroresect-restore-", dir=destination.parent)
    os.close(descriptor)
    staged = Path(name)
    try:
        shutil.copyfile(bundle / "database.sqlite3", staged)
        # Recheck the staged bytes, so a changed source cannot slip between verification and copy.
        if fingerprint(staged) != manifest["database_sha256"]:
            raise ValueError("Backup changed during restore")
        with closing(sqlite3.connect(staged)) as connection:
            with connection:
                interrupted = connection.execute(
                    "UPDATE jobs SET status='FAILED', stage='RESTORED_INTERRUPTED', updated_at=?, error=? WHERE status IN ('QUEUED', 'RUNNING')",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        json.dumps(
                            {
                                "code": "BACKUP_INTERRUPTED",
                                "message": "Restored from a snapshot. Submit a new job with a new idempotency key.",
                                "details": {},
                            }
                        ),
                    ),
                ).rowcount
            inspect_database(connection)
        flush(staged)
        # Hard-link publication is atomic and refuses existing files, including symlinks.
        os.link(staged, destination)
        sync_directory(destination.parent)
        return {
            "database": str(destination),
            "source_sha256": manifest["database_sha256"],
            "restored_sha256": fingerprint(staged),
            "interrupted_jobs": interrupted,
            "row_counts": manifest["row_counts"],
        }
    finally:
        staged.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("backup")
    save.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///./data/neuroresect.db")
    )
    save.add_argument("--output", required=True, type=Path)
    save.add_argument("--timeout", type=float, default=60)
    check = commands.add_parser("verify")
    check.add_argument("bundle", type=Path)
    recover = commands.add_parser("restore")
    recover.add_argument("bundle", type=Path)
    recover.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup(args.database_url, args.output, args.timeout)
        elif args.command == "verify":
            result = verify(args.bundle)
        else:
            result = restore(args.bundle, args.destination)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f"Backup operation failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
