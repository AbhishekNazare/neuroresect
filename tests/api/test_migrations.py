from concurrent.futures import ThreadPoolExecutor

import pytest
from neuroresect_api.backups import backup, restore, verify
from neuroresect_api.baseline_schema import Base as Baseline
from neuroresect_api.database import Database
from neuroresect_api.migrations import head_revision, status, upgrade
from neuroresect_api.repository import Repository
from sqlalchemy import inspect


def test_fresh_database_is_versioned_and_repeated_startup_is_idempotent(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'research.db'}")
    try:
        database.initialize()
        repository = Repository(database)
        scenario = repository.create_scenario({"patient_id": "RESEARCH-001", "label": "Preserve"})
        database.initialize()
        assert status(database.engine)["current"] == [head_revision()]
        assert repository.scenario(scenario["id"])["label"] == "Preserve"
    finally:
        database.close()


def test_legacy_adoption_preserves_rows_and_old_backup_restore(tmp_path):
    source = tmp_path / "legacy.db"
    database = Database(f"sqlite:///{source}")
    try:
        Baseline.metadata.create_all(database.engine)
        repository = Repository(database)
        scenario = repository.create_scenario({"patient_id": "RESEARCH-001", "label": "Legacy"})
        bundle = tmp_path / "backup"
        backup(f"sqlite:///{source}", bundle)
        with pytest.raises(RuntimeError, match="explicit upgrade"):
            database.initialize()
        with pytest.raises(RuntimeError, match="Unversioned"):
            upgrade(database.engine)
        assert "alembic_version" not in inspect(database.engine).get_table_names()
        upgraded = upgrade(database.engine, allow_legacy=True)
        assert upgraded["current"] == [head_revision()]
        assert repository.scenario(scenario["id"])["label"] == "Legacy"
        assert verify(bundle)["format"] == "neuroresect-sqlite-backup-v1"
        restored = tmp_path / "restored.db"
        restore(bundle, restored)
        restored_db = Database(f"sqlite:///{restored}")
        try:
            upgrade(restored_db.engine, allow_legacy=True)
            restored_db.initialize()
            assert Repository(restored_db).scenario(scenario["id"])["label"] == "Legacy"
        finally:
            restored_db.close()
    finally:
        database.close()


def test_schema_drift_and_unknown_revisions_are_not_silently_accepted(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'drift.db'}")
    try:
        Baseline.metadata.create_all(database.engine)
        with database.engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE scenarios ADD COLUMN unexpected TEXT")
        with pytest.raises(RuntimeError, match="adoption refused"):
            upgrade(database.engine, allow_legacy=True)
        assert "alembic_version" not in inspect(database.engine).get_table_names()
    finally:
        database.close()
    database = Database(f"sqlite:///{tmp_path / 'future.db'}")
    try:
        database.initialize()
        with database.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='future_revision'")
        with pytest.raises(RuntimeError, match="explicit upgrade"):
            database.initialize()
    finally:
        database.close()


def test_concurrent_fresh_startup_serializes_schema_creation(tmp_path):
    url = f"sqlite:///{tmp_path / 'parallel.db'}"

    def start(_):
        database = Database(url)
        try:
            database.initialize()
            return status(database.engine)["current"]
        finally:
            database.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(start, range(3))) == [[head_revision()]] * 3


def test_versioned_snapshot_remains_verifiable_and_restorable(tmp_path):
    url = f"sqlite:///{tmp_path / 'versioned.db'}"
    database = Database(url)
    database.initialize()
    database.close()
    bundle = tmp_path / "backup"
    backup(url, bundle)
    assert verify(bundle)["schema_revision"] == head_revision()
    restore(bundle, tmp_path / "restored.db")
    restored = Database(f"sqlite:///{tmp_path / 'restored.db'}")
    try:
        restored.initialize()
    finally:
        restored.close()


def test_failed_sqlite_migration_rolls_back_schema_and_revision(tmp_path, monkeypatch):
    from neuroresect_api import migrations

    database = Database(f"sqlite:///{tmp_path / 'failure.db'}")

    def fail(config, revision):
        config.attributes["connection"].exec_driver_sql("CREATE TABLE partial_change (value TEXT)")
        raise RuntimeError("Deliberate migration failure")

    monkeypatch.setattr(migrations.command, "upgrade", fail)
    try:
        with pytest.raises(RuntimeError, match="Deliberate"):
            upgrade(database.engine)
        assert inspect(database.engine).get_table_names() == []
    finally:
        database.close()


def test_upgrade_from_first_revision_preserves_queued_job(tmp_path):
    from alembic import command
    from neuroresect_api.migrations import BASELINE, configuration
    from neuroresect_api.repository import utcnow

    database = Database(f"sqlite:///{tmp_path / 'prior.db'}")
    try:
        with database.engine.begin() as connection:
            command.upgrade(configuration(connection), BASELINE)
            connection.execute(
                Baseline.metadata.tables["jobs"]
                .insert()
                .values(
                    id="JOB-prior",
                    kind="simulation",
                    scenario_id="SCN-prior",
                    executor="celery",
                    status="QUEUED",
                    progress=0,
                    stage="QUEUED",
                    payload={},
                    result=None,
                    error=None,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                    idempotency_scope=None,
                    request_hash="fixture",
                )
            )
        with pytest.raises(RuntimeError, match="explicit upgrade"):
            database.initialize()
        upgrade(database.engine)
        job = Repository(database).job("JOB-prior")
        assert job["status"] == "QUEUED"
        assert job["dispatch_attempts"] == 0
        assert Repository(database).due_deliveries() == ["JOB-prior"]
    finally:
        database.close()
