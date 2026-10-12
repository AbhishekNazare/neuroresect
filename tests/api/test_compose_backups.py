import json
from pathlib import Path

import pytest
from neuroresect_api.database import Database
from neuroresect_api.recovery_admin import inspect_recovery
from neuroresect_api.repository import Repository

from scripts import compose_backup as backups


def test_recovery_inspection_finalizes_only_unfinished_jobs(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'recovery.db'}")
    database.initialize()
    repository = Repository(database)
    job, _ = repository.create_job("simulation", "SCN-saved", {}, "celery", None)
    try:
        before = inspect_recovery(database)
        assert before["row_counts"]["jobs"] == 1
        assert before["interrupted_jobs"] == 0
        assert repository.job(job["id"])["status"] == "QUEUED"
        finalized = inspect_recovery(database, finalize=True)
        assert finalized["interrupted_jobs"] == 1
        assert repository.job(job["id"])["error"]["code"] == "BACKUP_INTERRUPTED"
        assert inspect_recovery(database, finalize=True)["interrupted_jobs"] == 0
    finally:
        database.close()


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    def pg(*args, stdin=None, stdout=None):
        if args[0] == "pg_dump" and "--version" not in args:
            stdout.write(b"PGDMP-fixture-only")
        return b"pg_dump fixture"

    monkeypatch.setattr(backups, "pg", pg)
    monkeypatch.setattr(
        backups, "inspect_database", lambda *args, **kwargs: {"schema_revision": "fixture"}
    )
    path = tmp_path / "bundle"
    backups.backup(path)
    return path


def test_archive_corruption_is_rejected_before_creating_database(bundle, monkeypatch):
    (bundle / "database.dump").write_bytes(b"changed")
    calls = []
    monkeypatch.setattr(backups, "pg", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match="checksum"):
        backups.restore(bundle, "new_research")
    assert calls == []


def test_existing_database_error_prevents_restore(bundle, monkeypatch):
    calls = []

    def pg(*args, **kwargs):
        calls.append(args[0])
        if args[0] == "createdb":
            raise RuntimeError("already exists")

    monkeypatch.setattr(backups, "pg", pg)
    with pytest.raises(RuntimeError, match="already exists"):
        backups.restore(bundle, "existing_research")
    assert calls == ["pg_restore", "createdb"]


def test_failed_restore_keeps_new_database_and_never_drops_source(bundle, monkeypatch):
    calls = []

    def pg(*args, **kwargs):
        calls.append(args)
        if args[0] == "pg_restore" and "--list" not in args:
            raise RuntimeError("restore failed")

    monkeypatch.setattr(backups, "pg", pg)
    with pytest.raises(RuntimeError, match="retained for inspection"):
        backups.restore(bundle, "failed_recovery")
    assert not any("dropdb" in args or "--clean" in args for args in calls)
    assert (bundle / "database.dump").read_bytes() == b"PGDMP-fixture-only"


def test_manifest_contains_no_connection_or_record_data(bundle):
    manifest = backups.verify(bundle)
    assert set(manifest) == {
        "format",
        "created_at",
        "archive_sha256",
        "archive_bytes",
        "schema_revision",
        "pg_dump_version",
        "scope",
    }
    assert (bundle / "database.dump").stat().st_mode & 0o777 == 0o600
    assert json.loads((bundle / "manifest.json").read_text()) == manifest


@pytest.mark.parametrize("name", ["../research", "research;drop", "--help", "x" * 64, "Research"])
def test_invalid_database_names_fail_before_any_command(name, monkeypatch):
    monkeypatch.setattr(backups, "verify", lambda *_: pytest.fail("must validate name first"))
    with pytest.raises(ValueError):
        backups.restore(Path("unused"), name)
